(function () {
  var COLORS = ['#3987e5', '#d95926', '#199e70', '#c98500', '#d55181', '#008300', '#9085e9', '#e66767'];
  var GRID = '#2c2c2a';
  var TEXT = '#c3c2b7';
  var SURFACE = '#1a1a19';
  var FONT = 'system-ui, -apple-system, "Segoe UI", Helvetica, Arial, sans-serif';

  Chart.defaults.font.family = FONT;
  Chart.defaults.color = TEXT;

  function money(n) {
    return Math.round(n).toLocaleString('nl-NL');
  }

  window.X4Charts = {
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

    scatter: function (canvasId, points) {
      var el = document.getElementById(canvasId);
      if (!el) return;
      new Chart(el, {
        type: 'scatter',
        data: {
          datasets: [{
            data: points,
            backgroundColor: COLORS[0],
            pointRadius: 6,
            pointHoverRadius: 8,
          }],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
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
  };
})();
