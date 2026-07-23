(function () {
  var chips = Array.prototype.slice.call(document.querySelectorAll('.nav-chip'));
  var sections = Array.prototype.slice.call(document.querySelectorAll('.block'));
  if (!('IntersectionObserver' in window) || !chips.length) return;
  var io = new IntersectionObserver(function (entries) {
    entries.forEach(function (entry) {
      if (!entry.isIntersecting) return;
      var id = entry.target.id;
      chips.forEach(function (c) {
        c.classList.toggle('active', c.getAttribute('href') === '#' + id);
      });
    });
  }, { rootMargin: '-45% 0px -50% 0px', threshold: 0 });
  sections.forEach(function (s) { io.observe(s); });
})();
