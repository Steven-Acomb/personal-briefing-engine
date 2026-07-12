// Dynamic [[briefing.source]] rows: add from a <template>, remove per row.
(function () {
  const rows = document.getElementById("source-rows");
  const tpl = document.getElementById("source-row-tpl");
  const addBtn = document.getElementById("add-source");
  if (!rows || !tpl || !addBtn) return;

  addBtn.addEventListener("click", function () {
    rows.appendChild(tpl.content.cloneNode(true));
  });

  rows.addEventListener("click", function (e) {
    if (e.target.classList.contains("row-del")) {
      e.target.closest(".source-row").remove();
    }
  });
})();
