// 배경 안개 — 피그마의 Mist orb / Glass 뒤 도형 위치를 그대로 옮겼습니다.
(function () {
  var mist = document.getElementById('mist');
  if (!mist) return;
  var C = { l300: 'rgba(203,187,251,.75)', l200: 'rgba(224,214,255,.9)', v500: 'rgba(148,118,174,.38)' };
  // [left, top, size, color] (히어로 아래부터 시작하는 y 좌표)
  var orbs = [
    [-140,1164,420,'v500'],[1120,1148,480,'v500'],[260,1384,460,'l300'],[40,1618,520,'l300'],[760,1848,520,'l300'],
    [1000,2218,460,'l300'],[-100,2968,480,'v500'],[120,2788,460,'l300'],[1050,3132,420,'v500'],[820,3262,480,'v500'],
    [0,3832,520,'l300'],[1050,4532,460,'l300'],[300,4482,460,'l300'],[-80,5232,480,'v500'],[640,5382,480,'v500'],[1000,5932,420,'v500']
  ];
  var frag = document.createDocumentFragment();
  orbs.forEach(function (o) {
    var el = document.createElement('i');
    el.style.cssText = 'left:calc(50% - 720px + ' + o[0] + 'px);top:' + o[1] + 'px;width:' + o[2] + 'px;height:' + o[2] + 'px;background:' + C[o[3]];
    frag.appendChild(el);
  });
  mist.appendChild(frag);
})();

// FAQ — 한 번에 하나만 열기
document.querySelectorAll('details.faq-item').forEach(function (d, _, all) {
  d.addEventListener('toggle', function () {
    if (d.open) all.forEach(function (o) { if (o !== d) o.open = false; });
  });
});
