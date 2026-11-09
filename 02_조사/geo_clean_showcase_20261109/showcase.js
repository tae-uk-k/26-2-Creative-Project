if (new URLSearchParams(location.search).has('embed')) document.body.classList.add('embedded');
document.querySelectorAll('.tabs a').forEach(link => link.addEventListener('click', () => {
  document.querySelectorAll('.tabs a').forEach(tab => tab.classList.toggle('active', tab === link));
}));
const dialog = document.querySelector('#photo-dialog');
document.querySelectorAll('[data-photo]').forEach(button => button.addEventListener('click', () => {
  const positions = ['0 0', '100% 0', '0 100%', '100% 100%'];
  const photo = dialog.querySelector('.dialog-photo');
  photo.style.setProperty('--photo', button.style.getPropertyValue('--photo'));
  photo.style.backgroundPosition = positions[Number(button.dataset.photo)];
  dialog.querySelector('p').textContent = button.getAttribute('aria-label').replace(' 크게 보기', '');
  dialog.showModal();
}));
dialog.querySelector('.close-dialog').addEventListener('click', () => dialog.close());
dialog.addEventListener('click', event => { if (event.target === dialog) dialog.close(); });
