from flask import Flask
from flask import render_template
from stats.x4stats import X4stats
import plotly.graph_objects as go
from flask_bootstrap import Bootstrap

app = Flask(__name__)
app.config.from_pyfile('config.py')
app.debug = False
app.template_folder = 'templates'
app.static_folder = 'static'
Bootstrap(app)

colors = {
    'background': '#0a0a0a',
    'text': '#FFFFFF'
}
colors_bar = ['#005e85', '#f27800', '#c90c0f', '#85858b', '#eaaf32', '#f08971', '#cbcbd4']

x4stats = X4stats(app.config["SAVE_LOCATION"])


def get_ware_sales_pie(df):
    ware_sales_pie = go.Figure(
        data=[go.Pie(
            labels=df.ware,
            values=df.sales,
        )])
    ware_sales_pie.update_layout(
        title='Wares sold',
        plot_bgcolor=colors['background'],
        paper_bgcolor=colors['background'],
        font_color=colors['text'],
        separators='.,',
    )
    return ware_sales_pie.to_html()


def get_ware_costs_pie(df):
    ware_costs_pie = go.Figure(
        data=[go.Pie(
            labels=df.ware,
            values=df.costs,
        )])
    ware_costs_pie.update_layout(
        title='Wares bought',
        plot_bgcolor=colors['background'],
        paper_bgcolor=colors['background'],
        font_color=colors['text'],
        separators='.,',
    )
    return ware_costs_pie.to_html()


def get_profit_per_commander(df):
    profit_commander = go.Figure()
    profit_commander.add_trace(
        go.Histogram(
            x=df.commander_name,
            y=df.value,
            histfunc="sum",
            marker={"color": colors_bar[2]},
        )
    )
    profit_commander.update_layout(
        plot_bgcolor=colors['background'],
        paper_bgcolor=colors['background'],
        font_color=colors['text'],
        height=900,
        title='Ship and station trade value including subordinates',
        separators='.,',
        yaxis=dict(
            title="profitss",
        ),
        xaxis=dict(
            title="commander",
            rangeslider=dict(
                visible=True
            ),
            type='category'
        )
    )
    return profit_commander.to_html()


def get_scatter_margin_profit(df):
    fig = go.Figure()

    # Add traces
    fig.add_trace(
        go.Scatter(
            x=df["value"],
            y=df["margin"],
            mode='markers',
            name='markers',
            text=df["ship_name"]
        )
    )
    fig.update_layout(
        plot_bgcolor=colors['background'],
        paper_bgcolor=colors['background'],
        font_color=colors['text'],
        height=900,
        title='Profit (x-axis) and margin (y-axis)',
        xaxis_showgrid=False,
        yaxis_showgrid=False,
        separators='.,',
    )
    return fig.to_html()


def get_table_per_ship(df):
    fig = go.Figure(data=[go.Table(
        header=dict(values=list(df.columns),
                    fill_color=colors['background'],
                    font_color=colors['text'],
                    align='left'),
        cells=dict(
            values=[
                df["ship_id"]
                , df["ship_class"]
                , df["commander_name"]
                , df["ship_code"]
                , df["ship_name"]
                , df["ship_type"]
                , df["value"]
                , df["sales"]
                , df["costs"]
                , df["volume"]
                , df["margin"]
               ],
            fill_color=colors['background'],
            font_color=colors['text'],
            align='left'))
    ])
    fig.update_layout(
        plot_bgcolor=colors['background'],
        paper_bgcolor=colors['background'],
        height=900,

    )
    return fig.to_html()


@app.route('/', methods=['GET'])
def index():
    return ''


@app.route('/stats', methods=['GET'])
@app.route('/stats/<hours>', methods=['GET'])
def stats(hours=None):
    df_sales = x4stats.get_df_sales(hours)
    df_per_ship = x4stats.get_df_per_ship(hours)

    game_time = str(round(x4stats.get_game_time() / 3600, 2))
    profit = f'{int(x4stats.get_profit(df_sales)):,}'.replace(',', '.')
    w_sales_pie = get_ware_sales_pie(df_sales)
    w_costs_pie = get_ware_costs_pie(df_sales)
    profit_histogram = get_profit_per_commander(df_sales)
    scatter_margin_profit = get_scatter_margin_profit(df_per_ship)
    table_per_ship = get_table_per_ship(df_per_ship)

    hours_par = "all time"
    if hours:
        hours_par = str(hours) + " hours"
    return render_template(
        'index.html',
        profit_histogram=profit_histogram,
        w_sales_pie=w_sales_pie,
        w_costs_pie=w_costs_pie,
        scatter_margin_profit=scatter_margin_profit,
        game_time=game_time,
        profit=profit,
        hours=hours_par,
        table_per_ship=table_per_ship
    )


def main():
    app.run(host='127.0.0.1', port=2992, threaded=True, debug=False)


if __name__ == '__main__':
    main()