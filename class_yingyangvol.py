# class_yingyangvol.py

import numpy as np
import pandas as pd
import pyupbit  
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import os
import requests
from notion_client import Client

# tkinter의 NO를 대체할 상수 정의 (필요 시)
NO = False  # 또는 필요한 다른 값으로 정의

class YingYangTradingBot:
   
    def __init__(self, symbol, interval, count, ema=True, window=20, span=10):
        self.symbol = symbol
        self.interval = interval
        self.count = count
        self.ema = ema
        self.window = window
        self.span = span
        self.price = None
        self.ying_yang_vol = None
        self.pan_bands = None
        self.signals = None
        self.backtest_result = None
        self.last_signal = None
    
    
    def download_data(self):
        df = pyupbit.get_ohlcv(self.symbol, self.interval, self.count)
        self.price = df
        return self.price

    def calculate_volatility(self):
       
        price_close = self.price['close']
        price_high = self.price['high']
        price_low = self.price['low']

        if self.ema:
            ma = self.price['close'].ewm(span=self.window, adjust=False).mean()  
        else:
            ma = self.price['close'].rolling(window=self.window).mean()

        diff = price_close - ma
        slow_window = self.span

        yang_vol = np.sqrt((diff**2 * (diff > 0)).rolling(window=self.window).mean())
        ying_vol = np.sqrt((diff**2 * (diff <= 0)).rolling(window=self.window).mean())
        total_vol = np.sqrt(yang_vol**2 + ying_vol**2)
        YYL = ((yang_vol - ying_vol) / total_vol)*100
        YYL_slow = YYL.rolling(window=slow_window).mean()  

        self.ying_yang_vol = pd.DataFrame({
            'ma': ma,
            'yang_vol': yang_vol,
            'ying_vol': ying_vol,
            'total_vol': total_vol,
            'YYL': YYL,
            'YYL_slow': YYL_slow
        })

        return self.ying_yang_vol


    def calculate_pan_bands(self):
        ma = self.price['close'].ewm(span=self.span, adjust=False).mean()
        upper_band = ma + 2 * self.ying_yang_vol['yang_vol']
        lower_band = ma - 2 * self.ying_yang_vol['ying_vol']
        
        self.pan_bands = pd.DataFrame({
            'upper_band': upper_band,
            'lower_band': lower_band,
            'pan_river_up': (ma + upper_band) / 2,
            'pan_river_down': (ma + lower_band) / 2
        })

        return self.pan_bands

    
    def trading_signal(self):
        """
        YYL과 YYL_slow의 교차를 감지하여 매수 및 매도 신호를 생성합니다.
        Signal: 2 (Buy), -2 (Sell), 0 (No Signal)
        Position: 1 (Long), 0 (No Position)
        Entry_Price: 매수 가격
        Exit_Price: 매도 가격
        """
        # YYL과 YYL_slow가 계산되었는지 확인
        if self.ying_yang_vol is None or self.pan_bands is None:
            raise ValueError("Volatility and Pan Bands must be calculated before generating signals.")
        
        df = self.ying_yang_vol.join(self.pan_bands).join(self.price['close'])

        # 신호 컬럼 초기화
        signals = pd.DataFrame(index=df.index, columns=['Signal', 'Position', 'Entry_Price', 'Exit_Price'])
        signals = signals.fillna(0)  # 초기값 0으로 채우기

        position = 0
        entry_price = 0

        # Define status based on YYL and YYL_slow
        status = df.apply(
                lambda row: 1 if row['YYL'] > row['YYL_slow'] else (-1 if row['YYL'] < row['YYL_slow'] else 0),
                axis=1
            )
        prev_status = status.shift(1)

        for i in range(1, len(df)):
            current_status = status.iloc[i]
            previous_status = prev_status.iloc[i]

            signal_diff = current_status - previous_status

            if (signal_diff == 2 or signal_diff == 1) and df['YYL'].iloc[i] < -75:
                # 매수 신호 (Buy Signal)
                signals['Signal'].iloc[i] = 1
                signals['Entry_Price'].iloc[i] = df['close'].iloc[i]
                position = 1
            elif (signal_diff == -2 or signal_diff == -1) and df['YYL'].iloc[i] > 75:
                # 매도 신호 (Sell Signal)
                signals['Signal'].iloc[i] = -1
                signals['Exit_Price'].iloc[i] = df['close'].iloc[i]
                position = 0

            # 포지션 상태 기록 (Record Position Status)
            signals.loc[i, 'Position'] = position

        self.signals = signals
          
        return self.signals
    

    def get_last_signal(self):
        
        if self.signals is None:
            raise ValueError("Trading signals must be generated before last signal.")
        df = self.ying_yang_vol.join(self.pan_bands).join(self.price['close']).join(self.signals).dropna()
        
        symbol = self.symbol
        timestamp = df.index[-1]
        last_signal_value = df['Signal'].iloc[-1]
        last_signal_str = 'Buy' if last_signal_value == 1 else 'Sell' if last_signal_value == -1 else 'No Signal'
        last_entry_price = df['close'].iloc[-1]
            
        print(f"Last Signal: {last_signal_str}, Entry Price: {last_entry_price}, Timestamp: {timestamp}")
    
        last_signal_df = pd.DataFrame({
            'Ticker': [symbol],
            'last_signal': [last_signal_str],
            'timestamp': [timestamp],
            'entry_price': [last_entry_price]
        })
    
        self.last_signal = last_signal_df
        print(self.last_signal)

        self.send_telegram_message(f" Ticker: {symbol} | Last Signal: {last_signal_str}, Entry Price: {last_entry_price}, Timestamp: {timestamp}")
        return self.last_signal

    def notion_update(self):
        # Notion 클라이언트 초기화
        NOTION_API = os.environ.get('NOTION_API')
        DATABASE_ID = os.environ.get('DATABASE_ID')
        notion = Client(auth=NOTION_API)
        # 데이터베이스 ID 설정
        database_id = DATABASE_ID

        if self.last_signal is None:
            raise ValueError("Last signal must be generated before updating Notion.")

        # Extract data from last_signal
        signal_data = self.last_signal.iloc[0]
        ticker = signal_data['Ticker']
        last_signal = signal_data['last_signal']
        timestamp = signal_data['timestamp']
        entry_price = signal_data['entry_price']
        
        new_page = {
            "parent": {"database_id": database_id},
            "properties": {
                "Ticker": {"title": [{"text": {"content": ticker}}]},
                "Signal_time": {"rich_text": [{"text": {"content": timestamp.strftime('%Y-%m-%d %H:%M:%S')}}]},
                "Last_signal": {"rich_text": [{"text": {"content": last_signal}}]},
                "Entry_price": {"number": entry_price}
            }
        }
        response = notion.pages.create(**new_page)

        # 응답 출력 (선택 사항)
        print(response)


    def backtest(self, initial_balance=100000000, sl_percentage=0.02, tp_percentage=0.10, fee_rate=0.0001):
        """
        백테스트를 수행합니다.
        - initial_balance: 초기 자본
        - sl_percentage: 슬리핑 손절 비율 (예: 0.05 for 5%)
        - tp_percentage: 테이크 프로핏 비율 (예: 0.10 for 10%)
        - fee_rate: 거래 수수료 비율 (예: 0.0001 for 0.01%)
        """
        if self.signals is None:
            raise ValueError("Trading signals must be generated before backtesting.")
        
        df = self.ying_yang_vol.join(self.pan_bands).join(self.price['close']).join(self.signals).dropna()
        
        balance = initial_balance
        position = 0  # 0: no position, 1: long position
        entry_price = 0
        highest_price = 0
        sl = 0
        tp = 0
        pnl = 0
        balance_history = []
        pnl_history = []
        position_size = 0
        bt_buy_history = []
        bt_entry_price_history = []
        bt_sell_history = []
        bt_exit_price_history = []
        last_entry_price = np.nan
        last_exit_price = np.nan
        backtest_messages = []  # List to store backtest messages

        for i in range(len(df)):
            idx = df.index[i]
            close = df['close'].iloc[i]
            signal = df['Signal'].iloc[i]
            
            if i > 0:
                previous_close = df['close'].iloc[i-1]
            else:
                previous_close = close  # No change on first iteration
            
            # Initialize action flags
            bt_buy = 0
            bt_sell = 0
            bt_entry_price = last_entry_price
            bt_exit_price = last_exit_price
            
            if position == 0:
                if signal == 1:
                    # Calculate position size as balance divided by close price
                    position_size = balance / close
                    # Calculate entry fee
                    fee = position_size * close * fee_rate
                    # Deduct fee from balance
                    balance -= fee
                    # Set entry price
                    entry_price = close
                    last_entry_price = entry_price
                    # Initialize stop loss and take profit
                    sl = close * (1 - sl_percentage)
                    tp = close * (1 + tp_percentage)
                    # Update position to long
                    position = 1
                    bt_buy = 1
                    bt_entry_price = entry_price
                    backtest_messages.append(f"BUY at {idx} | Price: {entry_price:.2f} | Position size: {position_size:.2f} | Fee: {fee:.2f} | stop loss: {sl:.2f} | take profit: {tp:.2f} | balance: {balance:.2f}")
                    
            elif position == 1:
                # Calculate mark-to-market PnL
                pnl = (close - previous_close) * position_size
                balance += pnl
                
                # Update stop loss and take profit based on current close
                if close > entry_price:
                    sl = close * (1 - sl_percentage)
                    tp = close * (1 + tp_percentage)
                
                exit_trade = False
                exit_reason = ''
                
                # Check for stop loss
                if close <= sl:
                    exit_trade = True
                    exit_reason = 'Stop Loss'
                # Check for take profit
                elif close >= tp:
                    exit_trade = True
                    exit_reason = 'Take Profit'
                # Check for sell signal
                elif signal == -1:
                    exit_trade = True
                    exit_reason = 'Sell Signal'
                
                if exit_trade:
                    # Calculate exit fee
                    fee = position_size * close * fee_rate
                    # Calculate PnL from entry to exit
                    total_pnl = (close - entry_price) * position_size
                    # Update balance with PnL
                    balance += total_pnl
                    # Deduct exit fee
                    balance -= fee
                    bt_sell = -1
                    bt_exit_price = close
                    last_exit_price = bt_exit_price
                    backtest_messages.append(f"EXIT ({exit_reason}) at {idx} | Price: {close:.2f} | PnL: {total_pnl:.2f} | Fee: {fee:.2f}")
                    
                    # Reset position
                    position = 0
                    position_size = 0
                    entry_price = 0
                    sl = 0
                    tp = 0
            
            # Record balance history
            balance_history.append(balance)
            # Record buy and sell signals
            bt_buy_history.append(bt_buy)
            bt_entry_price_history.append(bt_entry_price)
            bt_sell_history.append(bt_sell)
            bt_exit_price_history.append(bt_exit_price)
    
        # 최종 결과 저장
        self.backtest_result = pd.DataFrame({
            'balance': balance_history,
            'bt_buy_history': bt_buy_history,
            'bt_entry_price_history': bt_entry_price_history,
            'bt_sell_history': bt_sell_history,
            'bt_exit_price_history': bt_exit_price_history
        }, index=df.index)

        return self.backtest_result, backtest_messages

    def send_telegram_message(self, message):
        """
        텔레그램 봇을 통해 메시지를 전송하는 함수.

        Args:
            token (str): 텔레그램 봇의 API 토큰.
            chat_id (str): 메시지를 보낼 대상의 채팅 ID.
            message (str): 전송할 메시지 내용.
        """
        TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')  # 예: '123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11'
        CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')        # 예: '123456789' 또는 '@your_channel_username'

        if not TELEGRAM_TOKEN or not CHAT_ID:
                print("Error: TELEGRAM_TOKEN and CHAT_ID must be set as environment variables.")
                exit(1)


        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {
            'chat_id': CHAT_ID,
            'text': message,
            'parse_mode': 'Markdown'  # 메시지 포맷 설정 (옵션)
        }
        
        try:
            response = requests.post(url, data=payload)
            response.raise_for_status()  # HTTP 에러 발생 시 예외 발생
            result = response.json()
            if not result.get('ok'):
                print(f"Error sending message: {result}")
            else:
                print("Message sent successfully.")
        except requests.exceptions.HTTPError as http_err:
            print(f"HTTP error occurred: {http_err} - URL: {response.url}")
        except requests.exceptions.RequestException as e:
            print(f"HTTP Request failed: {e}")
    # 환경 변수에서 텔레그램 봇 토큰과 채팅 ID를 가져옵니다.


    def plot_results(self):
        
        
        if self.signals is None:
            raise ValueError("Signals must be generated before plotting.")

        if self.backtest_result is None:
            raise ValueError("Backtest must be performed before plotting.")
        
        df = self.price.join(self.signals).join(self.pan_bands).join(self.backtest_result)

        fig = make_subplots(rows=3, cols=1)

        fig.add_trace(go.Candlestick(
            x=df.index,
            open=df['open'],
            high=df['high'],
            low=df['low'],
            close=df['close'],
            name='Candlestick'
        ), row=1, col=1)
        
        fig.add_trace(go.Scatter(
            x=df.index,
            y=self.ying_yang_vol['ma'],
            mode='lines',
            name='MA',
            line=dict(color='purple')
        ), row=1, col=1)
        
        
        
        fig.add_trace(go.Scatter(
            x=df.index, 
            y=df['pan_river_up'], 
            mode='lines', 
            name='Pan River Fill',
            line=dict(color='rgba(0,0,0,0)'),
            showlegend=False,
            hoverinfo='skip'
        ), row=1, col=1)

        fig.add_trace(go.Scatter(
            x=df.index, 
            y=df['pan_river_down'], 
            mode='lines', 
            name='',
            line=dict(color='rgba(0,0,0,0)'),
            fill='tonexty',
            fillcolor='rgba(0, 0, 255, 0.1)',
            showlegend=False,
            hoverinfo='skip'
        ), row=1, col=1)

        # 매수 및 매도 신호 플롯
        buy_signals = df[df['bt_buy_history'] == 1]
        sell_signals = df[df['bt_sell_history'] == -1]
        fig.add_trace(go.Scatter(
            x=buy_signals.index, 
            y=buy_signals['low'] * 0.999,  # Buy signal just below the low of the candle
            mode='markers', 
            name='Buy Signal',
            marker=dict(symbol='triangle-up', color='green', size=12)
        ), row=1, col=1)
        fig.add_trace(go.Scatter(
            x=sell_signals.index, 
            y=sell_signals['high'] * 1.005,  # Sell signal just above the high of the candle
            mode='markers', 
            name='Sell Signal',
            marker=dict(symbol='triangle-down', color='red', size=12)
        ), row=1, col=1)

        
        fig.add_trace(go.Scatter(
            x=df.index,
            y=self.ying_yang_vol['YYL'],
            mode='lines',
            name='YYL',
            line=dict(color='blue')
        ), row=2, col=1)

        fig.add_trace(go.Scatter(
            x=df.index,
            y=self.ying_yang_vol['YYL_slow'],
            mode='lines',
            name='YYL_slow',
            line=dict(color='orange')
        ), row=2, col=1)
        
        fig.add_trace(go.Scatter(
            x=self.backtest_result.index,
            y=self.backtest_result['balance'],
            mode='lines',
            name='Balance'
        ), row=3, col=1)
        
        fig.update_xaxes(title_text='Time', row=3, col=1)
        fig.update_yaxes(title_text='Balance (KRW)', row=3, col=1)

        fig.update_layout(
            title='Price with Pan Bands and Trading Signals',
            xaxis_title='Time',
            yaxis_title='Price (KRW)',
            legend=dict(x=1, y=1, xanchor='left', yanchor='bottom'),  # Move legend to top right
            template='plotly_white',
            width=1000,
            height=1200,  # Increased height to allocate more space for the candle chart
            hovermode='x unified',
            xaxis_rangeslider_visible=False,
            xaxis2=dict(matches='x'),
            xaxis3=dict(matches='x')
        )

        return fig
