document.querySelectorAll('[data-rotation-files]').forEach((input) => {
  const form = input.closest('form');
  const feedback = form.querySelector('[data-upload-feedback]');
  const button = form.querySelector('button[type="submit"]');

  input.addEventListener('change', () => {
    const count = input.files.length;
    feedback.textContent = count ? `${count} frame${count === 1 ? '' : 's'} selected` : '';
    feedback.classList.toggle('is-invalid', count > 0 && (count < 24 || count > 36));
  });

  form.addEventListener('submit', (event) => {
    const count = input.files.length;
    if (count < 24 || count > 36) {
      event.preventDefault();
      feedback.textContent = 'Select a complete set of 24–36 frames.';
      feedback.classList.add('is-invalid');
      input.focus();
      return;
    }
    button.disabled = true;
    button.textContent = 'Optimizing frames...';
  });
});

document.querySelectorAll('[data-model-file]').forEach((input) => {
  const form = input.closest('form');
  const feedback = form.querySelector('[data-model-upload-feedback]');
  const button = form.querySelector('button[type="submit"]');
  const maxBytes = 50 * 1024 * 1024;

  input.addEventListener('change', () => {
    const file = input.files[0];
    if (!file) {
      feedback.textContent = '';
      return;
    }
    const extension = file.name.split('.').pop().toLowerCase();
    const valid = ['glb', 'gltf'].includes(extension) && file.size <= maxBytes;
    feedback.textContent = valid
      ? `${file.name} · ${(file.size / 1048576).toFixed(1)} MB`
      : 'Choose a GLB or glTF file smaller than 50 MB.';
    feedback.classList.toggle('is-invalid', !valid);
  });

  form.addEventListener('submit', (event) => {
    const file = input.files[0];
    const extension = file?.name.split('.').pop().toLowerCase();
    if (!file || !['glb', 'gltf'].includes(extension) || file.size > maxBytes) {
      event.preventDefault();
      feedback.textContent = 'Choose a valid GLB or glTF model smaller than 50 MB.';
      feedback.classList.add('is-invalid');
      input.focus();
      return;
    }
    button.disabled = true;
    button.textContent = 'Validating model…';
  });
});
