(function () {
  const KEY = 'oneStarAccessibility';
  const defaults = { fontLarge: false, serif: false, scheme: 'normal', hideImages: false };
  const getState = () => ({ ...defaults, ...(JSON.parse(localStorage.getItem(KEY) || '{}')) });
  const save = s => localStorage.setItem(KEY, JSON.stringify(s));
  const apply = () => {
    const s = getState();
    document.documentElement.classList.toggle('font-large', s.fontLarge);
    document.documentElement.classList.toggle('serif', s.serif);
    document.documentElement.classList.toggle('hide-images', s.hideImages);
    document.documentElement.classList.remove('scheme-white-black', 'scheme-black-yellow');
    if (s.scheme !== 'normal') document.documentElement.classList.add('scheme-' + s.scheme);
    const status = document.getElementById('accessibility-status');
    if (status) status.textContent = `Шрифт: ${s.fontLarge ? '1.5×' : 'обычный'} | ${s.serif ? 'с засечками' : 'без засечек'} | Схема: ${s.scheme === 'normal' ? 'обычная' : s.scheme === 'white-black' ? 'чёрный на белом' : 'жёлтый на чёрном'} | Изображения: ${s.hideImages ? 'скрыты' : 'показаны'}`;
  };
  window.toggleFontSize = () => { const s=getState(); s.fontLarge=!s.fontLarge; save(s); apply(); };
  window.toggleSerif = () => { const s=getState(); s.serif=!s.serif; save(s); apply(); };
  window.setScheme = scheme => { const s=getState(); s.scheme=scheme; save(s); apply(); };
  window.toggleImages = () => { const s=getState(); s.hideImages=!s.hideImages; save(s); apply(); };
  window.resetAccessibility = () => { save({...defaults}); apply(); };
  document.addEventListener('DOMContentLoaded', apply);
})();
