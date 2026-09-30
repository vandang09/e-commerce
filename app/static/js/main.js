const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content || '';
const toastStack = document.querySelector('#toast-stack');

function showToast(message, kind = 'success') {
  if (!toastStack) return;
  const toast = document.createElement('div');
  toast.className = `toast toast-${kind}`;
  toast.textContent = message;
  toastStack.append(toast);
  window.setTimeout(() => toast.remove(), 3600);
}

async function postJSON(url, payload) {
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
    body: JSON.stringify(payload),
  });
  const result = await response.json();
  if (!response.ok || !result.success) throw new Error(result.message || 'Something went wrong. Please try again.');
  return result;
}

function syncCartSummary(cartCount) {
  const badge = document.querySelector('#cart-count');
  if (badge && Number.isInteger(cartCount)) badge.textContent = cartCount;
  const rows = [...document.querySelectorAll('[data-cart-item]')];
  const subtotal = rows.reduce((sum, row) => {
    const quantity = Number(row.querySelector('[data-cart-quantity]')?.value || 0);
    return sum + Number(row.dataset.unitPrice) * quantity;
  }, 0);
  const subtotalElement = document.querySelector('#cart-subtotal');
  if (subtotalElement) subtotalElement.textContent = `₫${new Intl.NumberFormat('vi-VN').format(subtotal)}`;
  const shippingElement = document.querySelector('#cart-shipping');
  if (shippingElement) shippingElement.textContent = subtotal >= 500000 ? 'Free' : '₫25,000 at checkout';
}

document.querySelectorAll('[data-add-cart]').forEach((button) => {
  button.addEventListener('click', async () => {
    button.disabled = true;
    const originalText = button.textContent;
    button.textContent = 'Adding...';
    const quantityInput = button.dataset.quantityInput ? document.getElementById(button.dataset.quantityInput) : null;
    try {
      const result = await postJSON('/api/cart/add', {
        product_id: Number(button.dataset.addCart),
        quantity: quantityInput ? Number(quantityInput.value) : 1,
      });
      syncCartSummary(result.cart_count);
      showToast(result.message);
    } catch (error) {
      showToast(error.message, 'error');
    } finally {
      button.disabled = false;
      button.textContent = originalText;
    }
  });
});

document.querySelectorAll('[data-wishlist]').forEach((button) => {
  button.addEventListener('click', async () => {
    button.disabled = true;
    try {
      const result = await postJSON('/api/wishlist/toggle', { product_id: Number(button.dataset.wishlist) });
      button.classList.toggle('is-active', result.active);
      button.textContent = result.active ? '♥' : '♡';
      showToast(result.active ? 'Saved to your list.' : 'Removed from your list.');
    } catch (error) {
      showToast(error.message, 'error');
    } finally {
      button.disabled = false;
    }
  });
});

document.querySelectorAll('[data-cart-quantity]').forEach((input) => {
  input.addEventListener('change', async () => {
    const itemId = Number(input.dataset.cartQuantity);
    input.disabled = true;
    try {
      const result = await postJSON('/api/cart/update', { item_id: itemId, quantity: Number(input.value) });
      const lineTotal = document.querySelector(`[data-line-total="${itemId}"]`);
      if (lineTotal) lineTotal.textContent = `₫${new Intl.NumberFormat('vi-VN').format(result.subtotal)}`;
      syncCartSummary(result.cart_count);
      showToast('Bag updated.');
    } catch (error) {
      showToast(error.message, 'error');
      window.location.reload();
    } finally {
      input.disabled = false;
    }
  });
});

document.querySelectorAll('[data-remove-cart]').forEach((button) => {
  button.addEventListener('click', async () => {
    button.disabled = true;
    const dialog = document.querySelector('#confirm-dialog');
    const confirmed = dialog ? await new Promise((resolve) => {
      dialog.addEventListener('close', () => resolve(dialog.returnValue === 'confirm'), { once: true });
      dialog.showModal();
    }) : true;
    if (!confirmed) {
      button.disabled = false;
      return;
    }
    try {
      const result = await postJSON('/api/cart/remove', { item_id: Number(button.dataset.removeCart) });
      button.closest('[data-cart-item]')?.remove();
      syncCartSummary(result.cart_count);
      showToast(result.message);
      if (!document.querySelector('[data-cart-item]')) window.location.reload();
    } catch (error) {
      showToast(error.message, 'error');
      button.disabled = false;
    }
  });
});

const menuButton = document.querySelector('.menu-toggle');
const categoryNav = document.querySelector('.category-nav');
menuButton?.addEventListener('click', () => {
  const isOpen = categoryNav.classList.toggle('is-open');
  menuButton.setAttribute('aria-expanded', String(isOpen));
});

const themeButton = document.querySelector('[data-theme-toggle]');
themeButton?.addEventListener('click', () => {
  const nextTheme = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
  document.documentElement.dataset.theme = nextTheme;
  themeButton.setAttribute('aria-label', `Switch to ${nextTheme === 'dark' ? 'light' : 'dark'} theme`);
  try {
    localStorage.setItem('morrow-theme', nextTheme);
  } catch (error) {
    showToast('Theme changed for this visit only.', 'info');
  }
});

const headerShell = document.querySelector('.header-shell');
const updateHeader = () => headerShell?.classList.toggle('is-scrolled', window.scrollY > 12);
window.addEventListener('scroll', updateHeader, { passive: true });
updateHeader();

if ('IntersectionObserver' in window && !window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
  document.documentElement.classList.add('js-motion');
  const sectionObserver = new IntersectionObserver((entries, observer) => {
    entries.forEach((entry) => {
      if (entry.isIntersecting) {
        entry.target.classList.add('is-visible');
        observer.unobserve(entry.target);
      }
    });
  }, { threshold: 0.12 });
  document.querySelectorAll('.reveal-section').forEach((section) => sectionObserver.observe(section));
}

window.setTimeout(() => {
  document.querySelectorAll('.toast').forEach((toast) => toast.classList.add('toast-leaving'));
}, 3200);
