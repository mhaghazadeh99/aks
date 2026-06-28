const sidebar = document.getElementById("sidebar");
const toggleBtn = document.getElementById("toggleSidebar");
const darkToggle = document.getElementById("darkToggle");

/* =======================
   SIDEBAR COLLAPSE
======================= */
toggleBtn?.addEventListener("click", () => {
  sidebar.classList.toggle("collapsed");
});

/* =======================
   DARK MODE
======================= */
if (localStorage.getItem("dark") === "true") {
  document.body.classList.add("dark");
}

darkToggle?.addEventListener("click", () => {
  document.body.classList.toggle("dark");

  localStorage.setItem(
    "dark",
    document.body.classList.contains("dark")
  );
});

function getCSRFToken() {
    return document.querySelector('meta[name="csrf-token"]').content;
}