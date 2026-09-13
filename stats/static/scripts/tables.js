(function () {
  function cellValue(row, idx) {
    var cell = row.children[idx];
    if (cell.dataset.sortValue !== undefined) {
      return parseFloat(cell.dataset.sortValue);
    }
    return cell.textContent.trim().toLowerCase();
  }

  function sortRows(table, colIdx, asc) {
    var tbody = table.tBodies[0];
    var rows = Array.prototype.slice.call(tbody.rows);
    rows.sort(function (a, b) {
      var va = cellValue(a, colIdx);
      var vb = cellValue(b, colIdx);
      if (typeof va === 'number' && typeof vb === 'number') {
        if (isNaN(va)) return 1;
        if (isNaN(vb)) return -1;
        return asc ? va - vb : vb - va;
      }
      va = String(va);
      vb = String(vb);
      return asc ? va.localeCompare(vb) : vb.localeCompare(va);
    });
    rows.forEach(function (r) { tbody.appendChild(r); });
  }

  document.querySelectorAll('table.data-table').forEach(function (table) {
    if (!table.tHead) return;
    var headers = table.tHead.rows[0].cells;
    Array.prototype.forEach.call(headers, function (th, idx) {
      th.classList.add('sortable');
      th.addEventListener('click', function () {
        var asc = th.dataset.sortDir !== 'asc';
        Array.prototype.forEach.call(headers, function (h) {
          h.dataset.sortDir = '';
          h.classList.remove('sort-asc', 'sort-desc');
        });
        th.dataset.sortDir = asc ? 'asc' : 'desc';
        th.classList.add(asc ? 'sort-asc' : 'sort-desc');
        sortRows(table, idx, asc);
      });
    });
  });

  document.querySelectorAll('.table-search').forEach(function (input) {
    var table = document.getElementById(input.dataset.tableTarget);
    if (!table) return;
    input.addEventListener('input', function () {
      var q = input.value.trim().toLowerCase();
      Array.prototype.forEach.call(table.tBodies[0].rows, function (row) {
        row.hidden = !!q && row.textContent.toLowerCase().indexOf(q) === -1;
      });
    });
  });
})();
