import math
from flask import Flask
from flask import render_template
from stats.x4stats import X4stats
from pathlib import Path

app = Flask(__name__)
app.config.from_pyfile('config.py')
app.debug = False
app.template_folder = 'templates'
app.static_folder = 'static'

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


def number_formatter(n):
    return f'{int(n):,}'.replace(',', '.')


app.jinja_env.filters['money'] = number_formatter


def get_commander_chart_data(df):
    df = df.sort_values('value', ascending=False)
    return {
        'labels': [str(v) for v in df['commander_name']],
        'values': [float(v) for v in df['value']],
    }


def get_scatter_data(df):
    df = df.sort_values('value', ascending=False)
    if len(df) == 0:
        return []
    vol_min = float(df['volume'].min())
    vol_max = float(df['volume'].max())

    def radius(v):
        if vol_max == vol_min:
            return 10.0
        return 6.0 + (float(v) - vol_min) / (vol_max - vol_min) * 18.0

    return [
        {
            'x': float(row['value']),
            'y': float(row['margin']),
            'r': radius(row['volume']),
            'label': str(row['commander_name']),
        }
        for _, row in df.iterrows()
    ]


def get_ware_pie_data(df, column):
    df = df[df[column] > 0].sort_values(column, ascending=False)
    return {
        'labels': [str(v) for v in df['ware']],
        'values': [float(v) for v in df[column]],
    }


def get_ware_time_series_data(df):
    hours = sorted(df['hours_since_event'].unique(), reverse=True)
    wares = sorted(df['ware'].unique())
    labels = ['now' if h == 0 else f'-{int(h)}h' for h in hours]

    def series_for(column):
        pivoted = df.set_index(['hours_since_event', 'ware'])[column].unstack('ware')
        pivoted = pivoted.reindex(index=hours, columns=wares)
        return {w: [None if math.isnan(v) else float(v) for v in pivoted[w]] for w in wares}

    profit_by_ware = series_for('value')
    margin_by_ware = series_for('margin')
    volume_by_ware = series_for('volume')

    series = {
        w: {'profit': profit_by_ware[w], 'margin': margin_by_ware[w], 'volume': volume_by_ware[w]}
        for w in wares
    }
    return {'labels': labels, 'wares': wares, 'series': series}


def table_columns_ship(df):
    return [{'key': c, 'label': c, 'type': (
        'money' if c == 'value' else
        'number' if c in ('sales', 'costs', 'volume') else
        'percent' if c == 'margin' else
        'text'
    )} for c in df.columns]


TABLE_COLUMNS_INACTIVE = [
    {'key': 'commander_name', 'label': 'commander_name', 'type': 'text'},
    {'key': 'default_order', 'label': 'default_order', 'type': 'text'},
    {'key': 'ship_code', 'label': 'ship_code', 'type': 'text'},
    {'key': 'ship_name', 'label': 'ship_name', 'type': 'text'},
    {'key': 'ship_type', 'label': 'ship_type', 'type': 'text'},
    {'key': 'value', 'label': 'value', 'type': 'money'},
    {'key': 'volume', 'label': 'volume', 'type': 'number'},
]

TABLE_COLUMNS_WARE = [
    {'key': 'ware', 'label': 'ware', 'type': 'text'},
    {'key': 'volume', 'label': 'volume traded', 'type': 'number'},
    {'key': 'costs', 'label': 'total bought', 'type': 'number'},
    {'key': 'sales', 'label': 'total sales', 'type': 'number'},
    {'key': 'value', 'label': 'profit', 'type': 'money'},
    {'key': 'margin', 'label': 'margin', 'type': 'percent'},
]

TABLE_COLUMNS_TRANSACTIONS = [
    {'key': 'ship_name', 'label': 'name', 'type': 'text'},
    {'key': 'ship_code', 'label': 'code', 'type': 'text'},
    {'key': 'commander_name', 'label': 'commander', 'type': 'text'},
    {'key': 'time', 'label': 'time', 'type': 'number'},
    {'key': 'hours_since_event', 'label': 'hours ago', 'type': 'number'},
    {'key': 'ware', 'label': 'ware', 'type': 'text'},
    {'key': 'value', 'label': 'value', 'type': 'money'},
    {'key': 'volume', 'label': 'volume', 'type': 'number'},
]


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
    df_per_hour_ware = x4stats.get_df_per_hour_ware(hours)
    df_inactive_traders = x4stats.get_idle_traders_miners(hours)

    game_time = str(round(x4stats.get_game_time() / 3600, 2))
    profit_value = int(x4stats.get_profit(df_sales))
    profit = f'{profit_value:,}'.replace(',', '.')
    profit_class = 'positive' if profit_value > 0 else 'negative' if profit_value < 0 else ''

    total_sales = float(df_sales['sales'].sum())
    total_costs = float(df_sales['costs'].sum())
    margin_value = (total_sales - total_costs) / total_sales if total_sales else 0.0
    margin_class = 'positive' if margin_value > 0 else 'negative' if margin_value < 0 else ''
    active_count, eligible_count = x4stats.get_active_traders_count(hours)

    hours_par = "all time"
    hours_raw = ''
    if hours:
        hours_par = "past " + str(hours) + " hours"
        hours_raw = hours

    return render_template(
        'index.html',
        commander_chart=get_commander_chart_data(df_per_commander),
        scatter_data=get_scatter_data(df_per_commander),
        sales_pie=get_ware_pie_data(df_per_ware, 'sales'),
        costs_pie=get_ware_pie_data(df_per_ware, 'costs'),
        time_series=get_ware_time_series_data(df_per_hour_ware),
        game_time=game_time,
        profit=profit,
        profit_class=profit_class,
        total_sales=total_sales,
        total_costs=total_costs,
        margin_value=margin_value,
        margin_class=margin_class,
        active_count=active_count,
        eligible_count=eligible_count,
        hours=hours_par,
        hours_raw=hours_raw,
        inactive_columns=TABLE_COLUMNS_INACTIVE,
        inactive_rows=df_inactive_traders.to_dict('records'),
        ship_columns=table_columns_ship(df_per_ship),
        ship_rows=df_per_ship.to_dict('records'),
        ware_columns=TABLE_COLUMNS_WARE,
        ware_rows=df_per_ware.to_dict('records'),
    )


@app.route('/transactions', methods=['GET'])
@app.route('/transactions/<hours>', methods=['GET'])
def transactions(hours=None):
    df_sales = x4stats.get_df_sales_sorted(hours, filter_zero_value=True)
    hours_par = "all time"
    hours_raw = ''
    if hours:
        hours_par = "past " + str(hours) + " hours"
        hours_raw = hours
    return render_template(
        'transactions.html',
        transaction_columns=TABLE_COLUMNS_TRANSACTIONS,
        transaction_rows=df_sales.to_dict('records'),
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
