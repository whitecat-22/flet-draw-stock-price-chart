import time
import datetime
import flet as ft
from flet import *
from yahoo_finance_api2 import share
from yahoo_finance_api2.exceptions import YahooFinanceError
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import plotly.io as pio
from flet.plotly_chart import PlotlyChart

input_form = ft.TextField(hint_text='input stock code')
screen_mode = ft.Icon(ft.icons.TRIP_ORIGIN_ROUNDED),
chart = ft.Column()

today = datetime.date.today()


def main(page: ft.Page):

    def toggle_icon(e):
        page.theme_mode = "dark" if page.theme_mode == "light" else "light"
        toggle_dark_light_icon.selected = not toggle_dark_light_icon.selected
        page.update()

    toggle_dark_light_icon = ft.IconButton(
        icon="dark_mode",
        selected_icon = "light_mode",
        tooltip=f"switch light / dark mode",
        on_click=toggle_icon,
    )

    def button_clicked(e):
        """
        Generate dataframe of OHLCV with date by yahoo_finance_api2
        """
        def macd(df):
            FastEMA_period = 12  # 短期EMAの期間
            SlowEMA_period = 26  # 長期EMAの期間
            SignalSMA_period = 9  # SMAを取る期間
            df["MACD"] = df["close"].ewm(span=FastEMA_period).mean() - df["close"].ewm(span=SlowEMA_period).mean()
            df["Signal"] = df["MACD"].rolling(SignalSMA_period).mean()
            return df

        def rsi(df):
            # 前日との差分を計算
            df_diff = df["close"].diff(1)

            # 計算用のDataFrameを定義
            df_up, df_down = df_diff.copy(), df_diff.copy()

            # df_upはマイナス値を0に変換
            # df_downはプラス値を0に変換して正負反転
            df_up[df_up < 0] = 0
            df_down[df_down > 0] = 0
            df_down = df_down * -1

            # 期間14でそれぞれの平均を算出
            df_up_sma14 = df_up.rolling(window=14, center=False).mean()
            df_down_sma14 = df_down.rolling(window=14, center=False).mean()

            # RSIを算出
            df["RSI"] = 100.0 * (df_up_sma14 / (df_up_sma14 + df_down_sma14))

            return df

        print("--- start ---")
        # yahoo_finance_api2で過去2年分の株価を取得する
        stock_code = input_form.value
        print(f"--- stock_code = {stock_code} ---")
        my_share = share.Share(stock_code)
        symbol_data = None
        chart = ft.Column(None)

        def close_dlg(e):
            dlg_modal.open = False
            page.update()

        dlg_modal = ft.AlertDialog(
            modal=True,
            title=ft.Text("Alert"),
            content=ft.Text("An error has occurred and the process is terminated."),
            actions=[
                ft.TextButton("OK", on_click=close_dlg),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
            on_dismiss=lambda e: print("Modal dialog dismissed!"),
        )

        def open_dlg_modal(e):
            page.dialog = dlg_modal
            dlg_modal.open = True
            page.update()

        df = pd.DataFrame(symbol_data)
        try:
            symbol_data = my_share.get_historical(
                share.PERIOD_TYPE_YEAR, 2,
                share.FREQUENCY_TYPE_DAY, 1)

            df = pd.DataFrame(symbol_data)
            df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms")

            additional_dates = pd.date_range(
                start=df["datetime"].max()+datetime.timedelta(days=1),
                end=df["datetime"].max()+datetime.timedelta(days=25),
            )

            df = pd.concat([
                df,
                pd.DataFrame(additional_dates, columns=["datetime"])
            ], ignore_index=True)

            # 基準線
            high26 = df["high"].rolling(window=26).max()
            low26 = df["low"].rolling(window=26).min()
            df["base_line"] = (high26 + low26) / 2

            # 転換線
            high9 = df["high"].rolling(window=9).max()
            low9 = df["low"].rolling(window=9).min()
            df["conversion_line"] = (high9 + low9) / 2

            # 先行スパン1
            leading_span1 = (df["base_line"] + df["conversion_line"]) / 2
            df["leading_span1"] = leading_span1.shift(25)

            # 先行スパン2
            high52 = df["high"].rolling(window=52).max()
            low52 = df["low"].rolling(window=52).min()
            leading_span2 = (high52 + low52) / 2
            df["leading_span2"] = leading_span2.shift(25)

            # 遅行スパン
            df["lagging_span"] = df["close"].shift(-25)

            # 25日移動平均線
            df["SMA25"] = df["close"].rolling(window=25).mean()

            # 標準偏差
            df["std"] = df["close"].rolling(window=25).std()

            # ボリンジャーバンド
            df["2upper"] = df["SMA25"] + (2 * df["std"])
            df["2lower"] = df["SMA25"] - (2 * df["std"])
            df["3upper"] = df["SMA25"] + (3 * df["std"])
            df["3lower"] = df["SMA25"] - (3 * df["std"])

            # MACDを計算する
            df = macd(df)

            # RSIを算出
            df = rsi(df)

            # 非表示にする日付をリストアップ
            d_all = pd.date_range(start=df['datetime'].iloc[0],end=df['datetime'].iloc[-1])
            d_obs = [d.strftime("%Y-%m-%d") for d in df['datetime']]
            d_breaks = [d for d in d_all.strftime("%Y-%m-%d").tolist() if d not in d_obs]

            """
            Generate a six-month stock chart image with mplfinance
            """
            # The return value `datetime` from yahoo_finance_api2 is sorted by asc, so change it to desc for plot
            df = df.sort_values("datetime")

            # figを定義
            fig = make_subplots(rows=4, cols=1, shared_xaxes=True, vertical_spacing=0.005, row_width=[0.1, 0.2, 0.2, 0.5])

            # ローソク足：Candlestick
            fig.add_trace(
                go.Candlestick(x=df["datetime"], open=df["open"], high=df["high"], low=df["low"], close=df["close"], name="Prices"),
                row=1, col=1
            )

            # 一目均衡表
            fig.add_trace(go.Scatter(x=df["datetime"], y=df["base_line"], name="BaseLine", mode="lines", line=dict(color="purple")), row=1, col=1)
            fig.add_trace(go.Scatter(x=df["datetime"], y=df["conversion_line"], name="Conv.Line", mode="lines", line=dict(color="orange")), row=1, col=1)
            fig.add_trace(go.Scatter(x=df["datetime"], y=df["leading_span1"], name="AdvanceSpan1", mode="lines", fill=None, line=dict(width=0, color="gray"), showlegend=False), row=1, col=1)
            fig.add_trace(go.Scatter(x=df["datetime"], y=df["leading_span2"], name="AdvanceSpan2", mode="lines", fill='tonexty', line=dict(width=0, color="gray"), showlegend=False), row=1, col=1)
            fig.add_trace(go.Scatter(x=df["datetime"], y=df["lagging_span"], name="LaggingSpan", mode="lines", line=dict(color="turquoise")), row=1, col=1)

            # SMA
            fig.add_trace(go.Scatter(x=df["datetime"], y=df["SMA25"], name="SMA25", mode="lines", line=dict(color="magenta")), row=1, col=1)

            # ボリンジャーバンド
            fig.add_trace(
                go.Scatter(x=df["datetime"], y=df["2upper"], name="2σ", line=dict(width=1, color="pink")),
                row=1, col=1
            )
            fig.add_trace(
                go.Scatter(x=df["datetime"], y=df["2lower"], line=dict(width=1, color="pink"), showlegend=False),
                row=1, col=1
            )

            fig.add_trace(
                go.Scatter(x=df["datetime"], y=df["3upper"], name="3σ", line=dict(width=1, color="skyblue")),
                row=1, col=1
            )
            fig.add_trace(
                go.Scatter(x=df["datetime"], y=df["3lower"], line=dict(width=1, color="skyblue"), showlegend=False),
                row=1, col=1
            )

            # MACD
            # fig.add_trace(go.Scatter(x=df.index, y=df["MACD"], mode="lines", showlegend=False), row=2, col=1)
            # fig.add_trace(go.Scatter(x=df.index, y=df["Signal"], mode="lines", showlegend=False), row=2, col=1)
            fig.add_trace(
                go.Bar(x=df["datetime"], y=df["MACD"], name="MACD", marker_color="gray"),
                row=2, col=1
            )

            # RSI
            fig.add_trace(go.Scatter(x=df.index, y=df["RSI"], mode="lines", name="RSI", line=dict(color="blue")), row=3, col=1)

            # 出来高
            fig.add_trace(
                go.Bar(x=df["datetime"], y=df["volume"], name="Volume", marker_color="green"),
                row=4, col=1
            )

            # Layout
            fig.update_layout(
                title={
                    "text": f"Daily chart of {stock_code}",
                    "y":0.9,
                    "x":0.5,
                },
                height=600,
            )

            # y軸名を定義
            fig.update_yaxes(title_text="Prices", row=1, col=1, separatethousands=True)
            fig.update_yaxes(title_text="MACD", row=2, col=1, separatethousands=True)
            fig.update_yaxes(title_text="RSI", row=3, col=1, separatethousands=True)
            fig.update_yaxes(title_text="Vol", row=4, col=1, separatethousands=True)

            # 不要な日付を非表示にする
            fig.update_xaxes(
                rangebreaks=[dict(values=d_breaks)],
                tickformat='%Y/%m/%d',
            )

            fig.update(layout_xaxis_rangeslider_visible=False)

            page.controls.pop()
            page.update()
            chart = ft.Column(
                page.add(PlotlyChart(fig, expand=True)),
            )
            # page.update()
            input_form.value = ""
            input_form.focus()

        except YahooFinanceError as ye:
            open_dlg_modal(ye)
        except Exception as e:
            open_dlg_modal(e)

        print("--- end ---")

    page.title = "Flet example app, API with Django REST Framework"
    page.theme_mode = "dark"

    page.appbar = ft.AppBar(
        leading=ft.Icon(ft.icons.APPS),
        leading_width=40,
        title=ft.Text("Draw a stock price chart"),
        center_title=False,
        bgcolor=ft.colors.SURFACE_VARIANT,
        actions=[
            toggle_dark_light_icon,
        ],
    )
    page.add(
        input_form,
        ft.FilledButton("Draw a chart", icon="add_chart", on_click=button_clicked),
        chart,
    )

ft.app(target=main, view=ft.AppView.WEB_BROWSER)
