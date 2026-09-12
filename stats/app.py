from flask import Flask
from flask import render_template
from stats.x4stats import X4stats
import plotly.graph_objects as go
from flask_bootstrap import Bootstrap
from pathlib import Path

app = Flask(__name__)
app.config.from_pyfile('config.py')
app.debug = False
app.template_folder = 'templates'
app.static_folder = 'static'
Bootstrap(app)

colors = {
    'background': '#1a1a19',
    'text': '#FFFFFF',
    'secondary_text': '#c3c2b7',
    'grid': '#2c2c2a',
    'header': '#202020',
}
colors_bar = ['#3987e5', '#d95926', '#199e70', '#c98500', '#d55181', '#008300', '#9085e9', '#e66767']
font_family = 'system-ui, -apple-system, "Segoe UI", Helvetica, Arial, sans-serif'

# Check config
save_location = app.config["SAVE_LOCATION"]
p = Path(save_location)
if not p.exists():
    print("SAVE_LOCATION does not exist. Check config.py file.")
    quit()

# save ophalen
x4stats = X4stats(
    save_location=save_location
)


def render_fig(fig, first=False):
    return fig.to_html(
        full_html=False,
        include_plotlyjs=True if first else False,
        default_width='100%',
        config={'responsive': True, 'displaylogo': False},
    )


def base_layout(**overrides):
    layout = dict(
        plot_bgcolor=colors['background'],
        paper_bgcolor=colors['background'],
        font=dict(color=colors['text'], family=font_family, size=13),
        separators='.,',
        margin=dict(l=50, r=30, t=20, b=50),
        autosize=True,
    )
    layout.update(overrides)
    return layout


def get_ware_sales_pie(df, first=False):
    ware_sales_pie = go.Figure(
        data=[go.Pie(
            labels=df.ware,
            values=df.sales,
            marker=dict(colors=colors_bar, line=dict(color=colors['background'], width=2)),
            hole=0.45,
        )])
    ware_sales_pie.update_layout(**base_layout(
        legend=dict(font=dict(color=colors['secondary_text'])),
    ))
    ware_sales_pie.update_traces(textposition='inside', textfont_color=colors['text'])
    return render_fig(ware_sales_pie, first)


def get_ware_costs_pie(df, first=False):
    ware_costs_pie = go.Figure(
        data=[go.Pie(
            labels=df.ware,
            values=df.costs,
            marker=dict(colors=colors_bar, line=dict(color=colors['background'], width=2)),
            hole=0.45,
        )])
    ware_costs_pie.update_layout(**base_layout(
        legend=dict(font=dict(color=colors['secondary_text'])),
    ))
    ware_costs_pie.update_traces(textposition='inside', textfont_color=colors['text'])
    return render_fig(ware_costs_pie, first)


def get_profit_per_commander(df, first=False):
    profit_commander = go.Figure()
    profit_commander.add_trace(
        go.Histogram(
            x=df.commander_name,
            y=df.value,
            histfunc="sum",
            marker={"color": colors_bar[0]},
        )
    )
    profit_commander.update_layout(**base_layout(
        height=500,
        margin=dict(l=60, r=30, t=20, b=90),
        yaxis=dict(
            title="profit",
            gridcolor=colors['grid'],
            zerolinecolor=colors['grid'],
        ),
        xaxis=dict(
            title="commander",
            rangeslider=dict(visible=True, bgcolor=colors['header'], bordercolor=colors['grid']),
            type='category',
            gridcolor=colors['grid'],
        ),
    ))
    return render_fig(profit_commander, first)


def get_scatter_margin_profit(df, first=False):
    fig = go.Figure()

    fig.add_trace(
        go.Scatter(
            x=df["value"],
            y=df["margin"],
            mode='markers',
            name='commander',
            marker=dict(color=colors_bar[0], size=10, opacity=0.85,
                        line=dict(color=colors['background'], width=1)),
            text=df["commander_name"]
        )
    )
    fig.update_layout(**base_layout(
        height=500,
        xaxis=dict(title="profit", showgrid=False, zerolinecolor=colors['grid']),
        yaxis=dict(title="margin", showgrid=False, zerolinecolor=colors['grid']),
    ))
    return render_fig(fig, first)


def zebra_fill(n):
    return [colors['background'] if i % 2 == 0 else colors['header'] for i in range(n)]


def table_header(values):
    return dict(
        values=values,
        fill_color=colors['header'],
        font=dict(color=colors['text'], family=font_family, size=13),
        line_color=colors['grid'],
        align='left',
        height=34,
    )


def table_cells(values, n_rows):
    return dict(
        values=values,
        fill_color=[zebra_fill(n_rows)] * len(values),
        font=dict(color=colors['secondary_text'], family=font_family, size=12),
        line_color=colors['grid'],
        align='left',
        height=28,
    )


def get_table_inactive_traders_miners(df, first=False):
    fig = go.Figure(data=[go.Table(
        header=table_header(['commander_name', 'default_order', 'ship_code', 'ship_name', 'ship_type'
                              , 'value', 'volume']),
        cells=table_cells([
            df["commander_name"]
            , df["default_order"]
            , df["ship_code"]
            , df["ship_name"]
            , df["ship_type"]
            , df["value"].apply(number_formatter)
            , df["volume"].apply(number_formatter)
        ], len(df)))
    ])
    fig.update_layout(**base_layout(height=max(120, min(330, 60 + 28 * len(df)))))
    return render_fig(fig, first)


def get_table_per_ship(df, first=False):
    fig = go.Figure(data=[go.Table(
        header=table_header(list(df.columns)),
        cells=table_cells([
            df["ship_id"]
            , df["ship_class"]
            , df["commander_name"]
            , df["default_order"]
            , df["ship_code"]
            , df["ship_name"]
            , df["ship_type"]
            , df["value"].apply(number_formatter)
            , df["sales"].apply(number_formatter)
            , df["costs"].apply(number_formatter)
            , df["volume"].apply(number_formatter)
            , df["margin"]
        ], len(df))),
    ])
    fig.update_layout(**base_layout(height=900))
    return render_fig(fig, first)


def get_table_per_ware(df, first=False):
    fig = go.Figure(data=[go.Table(
        header=table_header(['ware', 'volume traded', 'total bought', 'total sales', 'profit']),
        cells=table_cells([
            df["ware"]
            , df["volume"].apply(number_formatter)
            , df["costs"].apply(number_formatter)
            , df["sales"].apply(number_formatter)
            , df["value"].apply(number_formatter)
        ], len(df))),
    ])
    fig.update_layout(**base_layout(height=max(120, min(700, 60 + 28 * len(df)))))
    return render_fig(fig, first)


def get_transactions_per_ship(df, first=False):
    cols = ["name", "code", "commander", "time", "hours_since_event", "ware", "value", "volume"]
    fig = go.Figure(data=[go.Table(
        header=table_header(cols),
        cells=table_cells([
            df["ship_name"]
            , df["ship_code"]
            , df["commander_name"]
            , df["time"]
            , df["hours_since_event"]
            , df["ware"]
            , df["value"].apply(number_formatter)
            , df["volume"].apply(number_formatter)
        ], len(df)))
    ])
    fig.update_layout(**base_layout(height=900))
    return render_fig(fig, first)


def number_formatter(n):
    return f'{int(n):,}'.replace(',', '.')


@app.route('/', methods=['GET'])
def index():
    return ''


@app.route('/stats', methods=['GET'])
@app.route('/stats/<hours>', methods=['GET'])
def stats(hours=None):
    df_sales = x4stats.get_df_sales(hours, filter_zero_value=True)
    df_per_ship = x4stats.get_df_per_ship(hours)
    df_per_commander = x4stats.get_df_per_commander(hours)
    df_per_ware = x4stats.get_df_per_ware(hours)
    df_inactive_traders = x4stats.get_idle_traders_miners(hours)

    game_time = str(round(x4stats.get_game_time() / 3600, 2))
    profit_value = int(x4stats.get_profit(df_sales))
    profit = f'{profit_value:,}'.replace(',', '.')
    profit_class = 'positive' if profit_value > 0 else 'negative' if profit_value < 0 else ''
    profit_histogram = get_profit_per_commander(df_sales, first=True)
    scatter_margin_profit = get_scatter_margin_profit(df_per_commander)
    w_sales_pie = get_ware_sales_pie(df_sales)
    w_costs_pie = get_ware_costs_pie(df_sales)
    inactive_traders = get_table_inactive_traders_miners(df_inactive_traders)
    table_per_ship = get_table_per_ship(df_per_ship)
    table_per_ware = get_table_per_ware(df_per_ware)

    hours_par = "all time"
    hours_raw = ''
    if hours:
        hours_par = "past " + str(hours) + " hours"
        hours_raw = hours
    return render_template(
        'index.html',
        profit_histogram=profit_histogram,
        w_sales_pie=w_sales_pie,
        w_costs_pie=w_costs_pie,
        scatter_margin_profit=scatter_margin_profit,
        game_time=game_time,
        profit=profit,
        profit_class=profit_class,
        hours=hours_par,
        hours_raw=hours_raw,
        inactive_traders=inactive_traders,
        table_per_ship=table_per_ship,
        table_per_ware=table_per_ware,
    )


@app.route('/transactions', methods=['GET'])
@app.route('/transactions/<hours>', methods=['GET'])
def transactions(hours=None):
    df_sales = x4stats.get_df_sales_sorted(hours, filter_zero_value=True)
    transactions_per_ship = get_transactions_per_ship(df_sales, first=True)
    hours_par = "all time"
    hours_raw = ''
    if hours:
        hours_par = "past " + str(hours) + " hours"
        hours_raw = hours
    return render_template(
        'transactions.html',
        transactions_per_ship=transactions_per_ship,
        hours=hours_par,
        hours_raw=hours_raw,
    )


@app.route('/reload', methods=['GET'])
@app.route('/reload/', methods=['GET'])
@app.route('/reload/<hours>', methods=['GET'])
def reload(hours=None):
    x4stats.check_for_new_file()
    return stats(hours)


def main():
    app.run(host='127.0.0.1', port=2992, threaded=True, debug=False)


if __name__ == '__main__':
    main()
