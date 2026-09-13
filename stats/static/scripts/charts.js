(function () {
  var COLORS = ['#3987e5', '#d95926', '#199e70', '#c98500', '#d55181', '#008300', '#9085e9', '#e66767'];
  var GRID = '#2c2c2a';
  var TEXT = '#c3c2b7';
  var MUTED = '#898781';
  var SURFACE = '#1a1a19';
  var FONT = 'system-ui, -apple-system, "Segoe UI", Helvetica, Arial, sans-serif';

  Chart.defaults.font.family = FONT;
  Chart.defaults.color = TEXT;

  function money(n) {
    return Math.round(n).toLocaleString('nl-NL');
  }

  function wareColor(index) {
    return COLORS[index % COLORS.length];
  }

  // Draws a text label next to each point of a bubble/scatter dataset whose
  // raw data carries a `.label`. No-op for chart types without that shape.
  // Points that land within the same ~10px bucket (e.g. several commanders
  // all at exactly 0 profit/0 margin) only get their first label drawn —
  // the rest stay reachable via tooltip instead of producing illegible overlap.
  Chart.register({
    id: 'directLabels',
    afterDatasetsDraw: function (chart) {
      var ctx = chart.ctx;
      var usedBuckets = {};
      chart.data.datasets.forEach(function (dataset, dsIndex) {
        var meta = chart.getDatasetMeta(dsIndex);
        if (meta.hidden) return;
        meta.data.forEach(function (point, i) {
          var raw = dataset.data[i];
          if (!raw || typeof raw.label !== 'string') return;
          var bucketKey = Math.round(point.x / 10) + ':' + Math.round(point.y / 10);
          if (usedBuckets[bucketKey]) return;
          usedBuckets[bucketKey] = true;
          var r = (point.options && point.options.radius) || 6;
          ctx.save();
          ctx.fillStyle = TEXT;
          ctx.font = '11px ' + FONT;
          ctx.textAlign = 'left';
          ctx.textBaseline = 'middle';
          ctx.fillText(raw.label, point.x + r + 4, point.y);
          ctx.restore();
        });
      });
    },
  });

  // Dashed zero-reference lines on bubble charts, so profit/loss and
  // positive/negative margin read at a glance.
  Chart.register({
    id: 'zeroLines',
    afterDraw: function (chart) {
      if (chart.config.type !== 'bubble') return;
      var ctx = chart.ctx;
      var area = chart.chartArea;
      var xZero = chart.scales.x.getPixelForValue(0);
      var yZero = chart.scales.y.getPixelForValue(0);
      ctx.save();
      ctx.strokeStyle = MUTED;
      ctx.setLineDash([4, 4]);
      ctx.lineWidth = 1;
      ctx.beginPath();
      if (xZero >= area.left && xZero <= area.right) {
        ctx.moveTo(xZero, area.top);
        ctx.lineTo(xZero, area.bottom);
      }
      if (yZero >= area.top && yZero <= area.bottom) {
        ctx.moveTo(area.left, yZero);
        ctx.lineTo(area.right, yZero);
      }
      ctx.stroke();
      ctx.restore();
    },
  });

  window.X4Charts = {
    wareColor: wareColor,

    bar: function (canvasId, labels, values) {
      var el = document.getElementById(canvasId);
      if (!el) return;
      new Chart(el, {
        type: 'bar',
        data: {
          labels: labels,
          datasets: [{
            data: values,
            backgroundColor: COLORS[0],
            borderRadius: 4,
            maxBarThickness: 48,
          }],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: { display: false },
            tooltip: { callbacks: { label: function (ctx) { return money(ctx.parsed.y); } } },
          },
          scales: {
            x: { grid: { color: GRID }, ticks: { color: TEXT } },
            y: { grid: { color: GRID }, ticks: { color: TEXT, callback: money }, beginAtZero: true },
          },
        },
      });
    },

    pie: function (canvasId, labels, values) {
      var el = document.getElementById(canvasId);
      if (!el) return;
      new Chart(el, {
        type: 'doughnut',
        data: {
          labels: labels,
          datasets: [{
            data: values,
            backgroundColor: COLORS,
            borderColor: SURFACE,
            borderWidth: 2,
          }],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          cutout: '55%',
          plugins: {
            legend: { position: 'right', labels: { color: TEXT, boxWidth: 12, padding: 12 } },
            tooltip: {
              callbacks: {
                label: function (ctx) {
                  var total = ctx.dataset.data.reduce(function (a, b) { return a + b; }, 0);
                  var pct = total ? ((ctx.parsed / total) * 100).toFixed(1) : '0';
                  return ctx.label + ': ' + money(ctx.parsed) + ' (' + pct + '%)';
                },
              },
            },
          },
        },
      });
    },

    // Profit (x) vs margin (y) per commander, bubble-sized by trade volume,
    // colored per commander, with the name drawn right next to each point.
    scatter: function (canvasId, points) {
      var el = document.getElementById(canvasId);
      if (!el) return;
      new Chart(el, {
        type: 'bubble',
        data: {
          datasets: [{
            data: points,
            backgroundColor: function (ctx) {
              return wareColor(ctx.dataIndex) + 'cc';
            },
            borderColor: SURFACE,
            borderWidth: 2,
            hoverBorderColor: TEXT,
          }],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          layout: { padding: { right: 90, top: 10, bottom: 10 } },
          plugins: {
            legend: { display: false },
            tooltip: {
              callbacks: {
                label: function (ctx) {
                  var p = ctx.raw;
                  return p.label + ': ' + money(p.x) + ' profit, ' + (p.y * 100).toFixed(1) + '% margin';
                },
              },
            },
          },
          scales: {
            x: {
              title: { display: true, text: 'profit', color: TEXT },
              grid: { color: GRID },
              ticks: { color: TEXT, callback: money },
            },
            y: {
              title: { display: true, text: 'margin', color: TEXT },
              grid: { color: GRID },
              ticks: { color: TEXT, callback: function (v) { return (v * 100).toFixed(0) + '%'; } },
            },
          },
        },
      });
    },

    // One line per ware, sharing a set of hour-bucket labels. `metricKey`
    // selects which field of each ware's series to plot ('profit'/'margin'/'volume').
    multiLine: function (canvasId, labels, wares, seriesByWare, metricKey, opts) {
      opts = opts || {};
      var el = document.getElementById(canvasId);
      if (!el) return;
      var percent = !!opts.percent;
      var formatY = function (v) { return percent ? (v * 100).toFixed(0) + '%' : money(v); };
      var datasets = wares.map(function (ware, i) {
        var color = wareColor(i);
        return {
          label: ware,
          data: seriesByWare[ware][metricKey],
          borderColor: color,
          backgroundColor: color,
          spanGaps: true,
          fill: false,
          tension: 0.25,
          pointRadius: 2,
          pointHoverRadius: 5,
          borderWidth: 2,
        };
      });
      return new Chart(el, {
        type: 'line',
        data: { labels: labels, datasets: datasets },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          interaction: { mode: 'nearest', intersect: false },
          plugins: {
            legend: { display: false },
            tooltip: {
              callbacks: {
                label: function (ctx) {
                  var v = ctx.parsed.y;
                  return ctx.dataset.label + ': ' + (v === null || v === undefined ? 'n/a' : formatY(v));
                },
              },
            },
          },
          scales: {
            x: { grid: { color: GRID }, ticks: { color: TEXT, maxRotation: 0, autoSkip: true } },
            y: { grid: { color: GRID }, ticks: { color: TEXT, callback: formatY } },
          },
        },
      });
    },
  };
})();
