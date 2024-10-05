import streamlit as st
import pyupbit
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from class_yingyangvol import YingYangTradingBot
from class_mrha import MRHATradingSystem

# 페이지 설정
st.set_page_config(page_title="Crypto Trading Backtester", layout="wide")

# 봇 실행을 위한 캐시된 함수들
@st.cache_data(ttl=600)
def run_ying_yang_bot(ticker, interval):
    try:
        bot = YingYangTradingBot(ticker, interval, count=300, ema=True, window=20, span=10)
        bot.download_data()
        bot.calculate_volatility()
        bot.calculate_pan_bands()
        bot.trading_signal()
        backtest_result, backtest_messages = bot.backtest()
        return bot, backtest_messages
    except Exception as e:
        st.error(f"Error in Ying Yang bot: {str(e)}")
        return None, None

@st.cache_data(ttl=600)
def run_mrha_bot(ticker, interval):
    try:
        bot = MRHATradingSystem(ticker, interval, count=300)
        bot.run_analysis()
        return bot
    except Exception as e:
        st.error(f"Error in MRHA bot: {str(e)}")
        return None

# 백테스트 메시지를 DataFrame으로 변환하는 함수
def parse_backtest_messages(messages):
    data = []
    for message in messages:
        parts = message.split(" | ")
        action_data = parts[0].split(" at ")
        action = action_data[0]
        timestamp = action_data[1]
        
        entry = {"Action": action, "Timestamp": timestamp}
        
        for part in parts[1:]:
            key, value = part.split(": ")
            entry[key.strip()] = float(value.strip())
        
        data.append(entry)
    
    return pd.DataFrame(data)

# 사이드바 설정
st.sidebar.title("Trading Bot Configuration")

# 트레이딩 봇 선택
bot_options = ["Ying Yang Volatility", "MRHA Fibonacci"]
selected_bot = st.sidebar.selectbox("Select Trading Bot", bot_options)

# 사용 가능한 티커 가져오기
try:
    tickers = pyupbit.get_tickers(fiat="KRW")
    default_ticker = "KRW-BTC" if "KRW-BTC" in tickers else tickers[0]
    selected_ticker = st.sidebar.selectbox("Select Cryptocurrency", tickers, index=tickers.index(default_ticker))
except Exception as e:
    st.sidebar.error(f"Error fetching tickers: {str(e)}")
    st.stop()

# 선택된 봇에 따른 시간 간격 선택
time_spans = ["minute1", "minute3", "minute5", "minute10", "minute15", "minute30", "minute60", "minute240", "day", "week", "month"]

if selected_bot == "Ying Yang Volatility":
    default_time_span = "minute30"
    selected_time_span = st.sidebar.selectbox("Select Time Span", time_spans, index=time_spans.index(default_time_span))
elif selected_bot == "MRHA Fibonacci":
    default_time_span = "day"
    selected_time_span = st.sidebar.selectbox("Select Time Span", time_spans, index=time_spans.index(default_time_span))

# 백테스팅 실행 버튼
if st.sidebar.button("Run Backtesting"):
    st.session_state.run_backtesting = True
    st.session_state.selected_bot = selected_bot
    st.session_state.selected_ticker = selected_ticker
    st.session_state.selected_time_span = selected_time_span
else:
    if 'run_backtesting' not in st.session_state:
        st.session_state.run_backtesting = False

# 메인 컨텐츠
st.title("Crypto Trading Backtester")

if st.session_state.get('run_backtesting', False):
    selected_bot = st.session_state.selected_bot
    selected_ticker = st.session_state.selected_ticker
    selected_time_span = st.session_state.selected_time_span

    if selected_bot == "Ying Yang Volatility":
        ying_yang_bot, ying_yang_backtest_messages = run_ying_yang_bot(selected_ticker, selected_time_span)
        
        if ying_yang_bot and ying_yang_backtest_messages:
            # Ying Yang Volatility 결과 표시
            st.header("Ying Yang Volatility Trading Bot Results")
            
            # 차트 표시
            st.subheader("Ying Yang Volatility Chart")
            fig_ying_yang = ying_yang_bot.plot_results()
            st.plotly_chart(fig_ying_yang, use_container_width=True)
            
            # 백테스트 결과 표시
            st.subheader("Ying Yang Volatility Backtest Results")
            initial_balance = 100000000  # 1억 원
            final_balance = ying_yang_bot.backtest_result['balance'].iloc[-1]
            total_return = (final_balance - initial_balance) / initial_balance * 100
            
            col1, col2, col3 = st.columns(3)
            col1.metric("Initial Balance", f"{initial_balance:,.0f} KRW")
            col2.metric("Final Balance", f"{final_balance:,.0f} KRW")
            col3.metric("Total Return", f"{total_return:.2f}%")
            
            # 백테스트 메시지 테이블 표시
            st.subheader("Ying Yang Volatility Backtest Messages")
            backtest_df = parse_backtest_messages(ying_yang_backtest_messages)
            st.dataframe(backtest_df, use_container_width=True)
    
    elif selected_bot == "MRHA Fibonacci":
        mrha_bot = run_mrha_bot(selected_ticker, selected_time_span)
        
        if mrha_bot:
            # MRHA Fibonacci 결과 표시
            st.header("MRHA Fibonacci Trading System Results")
            
            # 차트 표시
            st.subheader("MRHA Fibonacci Trading System Chart")
            fig_mrha = mrha_bot.plot_results()
            st.plotly_chart(fig_mrha, use_container_width=True)
            
            # 백테스트 결과 표시
            st.subheader("MRHA Fibonacci Trading System Backtest Results")
            mrha_results = mrha_bot.get_results()
            
            col1, col2, col3 = st.columns(3)
            col1.metric("Final Portfolio Value", f"{mrha_results['Final Portfolio Value']:,.0f} KRW")
            col2.metric("Total Return", f"{mrha_results['Total Return']:.2f}%")
            col3.metric("Sharpe Ratio", f"{mrha_results['Sharpe Ratio']:.2f}")
            
            col4, col5, col6 = st.columns(3)
            col4.metric("Annualized Return", f"{mrha_results['Annualized Return']:.2f}%")
            col5.metric("Max Drawdown", f"{mrha_results['Max Drawdown']:.2f}%")
            col6.metric("Total Trades", mrha_results['Total Trades'])
            
            # 트레이드 히스토리 표시
            st.subheader("MRHA Fibonacci Trading System Trade History")
            st.dataframe(mrha_bot.trades, use_container_width=True)
else:
    st.write("사이드바에서 'Run Backtesting' 버튼을 클릭하여 분석을 시작하세요.")

# 정보 메시지 표시
st.sidebar.info("Use the sidebar to configure the bot and run the backtesting.")
