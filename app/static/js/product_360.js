(() => {
  const ROTATION_SENSITIVITY = 5;
  const MIN_ZOOM = 1;
  const MAX_ZOOM = 2.2;
  const AUTO_FRAME_MS = 260;
  const FRAME_COUNT_PREVIEW = 36;

  document.querySelectorAll('[data-product-viewer]').forEach((viewer) => {
    const canvas = viewer.querySelector('[data-spin-canvas]');
    const context = canvas.getContext('2d', { alpha: false });
    const stage = viewer.querySelector('[data-spin-stage]');
    const frameData = JSON.parse(viewer.querySelector('[data-rotation-image-data]').textContent);
    const hasTrueFrames = frameData.length >= 24;
    const imageUrl = viewer.dataset.productImage;
    const images = hasTrueFrames ? frameData.map(() => new Image()) : [new Image()];
    const frameCount = hasTrueFrames ? images.length : FRAME_COUNT_PREVIEW;
    const loading = viewer.querySelector('[data-spin-loading]');
    const progress = viewer.querySelector('[data-spin-progress]');
    const progressLabel = viewer.querySelector('[data-spin-progress-label]');
    const ready = viewer.querySelector('[data-spin-ready]');
    const hint = viewer.querySelector('[data-spin-hint]');
    const autoButton = viewer.querySelector('[data-auto-rotate]');
    let position = 0;
    let zoom = MIN_ZOOM;
    let velocity = 0;
    let dragging = false;
    let pointerId = null;
    let lastX = 0;
    let lastMoveAt = 0;
    let lastTickAt = 0;
    let lastFrame = -1;
    let autoRotate = false;
    let resumeAutoAfterDrag = false;
    let resumeTimer = 0;
    let animationFrame = 0;
    let pinchDistance = 0;
    let hasInteracted = false;
    const activePointers = new Map();
    const sourceImage = new Image();
    sourceImage.src = imageUrl;
    const loaded = hasTrueFrames ? new Array(frameCount).fill(false) : [false];

    function wrapFrame(value) {
      return ((Math.round(value) % frameCount) + frameCount) % frameCount;
    }

    function requestDraw() {
      if (!animationFrame) animationFrame = requestAnimationFrame(drawFrame);
    }

    function drawImage(image, frameIndex, virtualSpin = false) {
      const width = canvas.width;
      const height = canvas.height;
      context.fillStyle = getComputedStyle(stage).getPropertyValue('--viewer-canvas-bg').trim() || '#f4f3ee';
      context.fillRect(0, 0, width, height);
      const fit = Math.min(width * 0.82 / image.naturalWidth, height * 0.82 / image.naturalHeight) * zoom;
      const drawWidth = image.naturalWidth * fit;
      const drawHeight = image.naturalHeight * fit;
      const angle = virtualSpin ? (frameIndex / frameCount) * Math.PI * 2 : 0;
      const horizontalScale = virtualSpin ? Math.max(0.075, Math.abs(Math.cos(angle))) * (Math.cos(angle) < 0 ? -1 : 1) : 1;
      const x = width / 2;
      const y = height / 2;
      context.save();
      context.translate(x, y);
      context.scale(horizontalScale, 1);
      context.shadowColor = 'rgba(35, 45, 37, 0.17)';
      context.shadowBlur = 22;
      context.shadowOffsetY = 14;
      context.drawImage(image, -drawWidth / 2, -drawHeight / 2, drawWidth, drawHeight);
      context.restore();
    }

    function drawFrame(now = 0) {
      animationFrame = 0;
      if (document.hidden) return;
      const delta = lastTickAt ? Math.min(now - lastTickAt, 48) : 16;
      lastTickAt = now;
      if (autoRotate) position += delta / AUTO_FRAME_MS;
      else if (!dragging && Math.abs(velocity) > 0.002) {
        position += velocity * delta;
        velocity *= Math.pow(0.91, delta / 16);
        if (Math.abs(velocity) <= 0.002) velocity = 0;
      }

      const frameIndex = wrapFrame(position);
      if (frameIndex !== lastFrame) {
        if (hasTrueFrames) {
          if (loaded[frameIndex]) drawImage(images[frameIndex], frameIndex);
          else {
            const nearest = loaded.findIndex(Boolean);
            if (nearest >= 0) drawImage(images[nearest], nearest);
          }
        } else if (sourceImage.complete && sourceImage.naturalWidth) {
          drawImage(sourceImage, frameIndex, true);
        }
        lastFrame = frameIndex;
      }
      if (autoRotate || Math.abs(velocity) > 0.002) animationFrame = requestAnimationFrame(drawFrame);
    }

    function stopAnimation() {
      if (animationFrame) cancelAnimationFrame(animationFrame);
      animationFrame = 0;
      lastTickAt = 0;
    }

    function setAutoRotate(active) {
      autoRotate = active;
      autoButton.setAttribute('aria-pressed', String(active));
      autoButton.setAttribute('aria-label', active ? 'Pause automatic rotation' : 'Start automatic rotation');
      autoButton.querySelector('span').textContent = active ? 'Pause' : 'Auto rotate';
      autoButton.firstChild.textContent = active ? 'Ⅱ ' : '▶ ';
      if (active) requestDraw();
      else if (!dragging && !velocity) stopAnimation();
    }

    function markInteracted() {
      if (!hasInteracted) {
        hasInteracted = true;
        hint.classList.add('is-dismissed');
      }
    }

    function zoomTo(nextZoom) {
      zoom = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, nextZoom));
      requestDraw();
    }

    function loadFrame(index) {
      return new Promise((resolve) => {
        const image = images[index];
        if (loaded[index]) return resolve(true);
        image.onload = () => { loaded[index] = true; resolve(true); };
        image.onerror = () => resolve(false);
        image.decoding = 'async';
        image.src = frameData[index];
      });
    }

    function preloadFrames() {
      if (!hasTrueFrames) {
        sourceImage.onload = () => { loaded[0] = true; drawImage(sourceImage, 0, true); ready.querySelector('[data-spin-ready-label]').textContent = 'Preview ready · single image'; ready.hidden = false; loading.hidden = true; };
        sourceImage.onerror = () => { ready.querySelector('[data-spin-ready-label]').textContent = 'Image unavailable'; ready.hidden = false; loading.hidden = true; };
        if (sourceImage.complete && sourceImage.naturalWidth) sourceImage.onload();
        return;
      }
      const order = Array.from({ length: frameCount }, (_, index) => index).sort((a, b) => {
        const distanceA = Math.min(a, frameCount - a);
        const distanceB = Math.min(b, frameCount - b);
        return distanceA - distanceB;
      });
      let cursor = 0;
      let completed = 0;
      const loadBatch = async () => {
        const batch = order.slice(cursor, cursor + 3);
        cursor += batch.length;
        await Promise.all(batch.map(async (index) => { if (await loadFrame(index)) completed += 1; }));
        progress.value = Math.round((completed / frameCount) * 100);
        progressLabel.textContent = `${progress.value}%`;
        requestDraw();
        if (cursor < frameCount) window.setTimeout(loadBatch, 0);
        else {
          const label = ready.querySelector('[data-spin-ready-label]');
          label.textContent = completed === frameCount ? `${frameCount} angles ready` : `${completed} of ${frameCount} angles ready`;
          ready.hidden = false;
          loading.hidden = true;
        }
      };
      loadBatch();
    }

    function showMode(mode) {
      viewer.querySelectorAll('[data-view-panel]').forEach((panel) => { panel.hidden = panel.dataset.viewPanel !== mode; });
      viewer.querySelectorAll('[data-view-mode]').forEach((button) => {
        const active = button.dataset.viewMode === mode;
        button.classList.toggle('is-active', active);
        button.setAttribute('aria-selected', String(active));
      });
      if (mode === 'spin') {
        preloadFrames();
        requestDraw();
        canvas.focus({ preventScroll: true });
      }
    }

    viewer.querySelectorAll('[data-view-mode]').forEach((button) => button.addEventListener('click', () => showMode(button.dataset.viewMode)));
    viewer.querySelector('[data-open-spin]').addEventListener('click', () => showMode('spin'));
    viewer.querySelectorAll('[data-frame-step]').forEach((button) => button.addEventListener('click', () => {
      markInteracted();
      position += Number(button.dataset.frameStep);
      velocity = 0;
      requestDraw();
    }));
    autoButton.addEventListener('click', () => setAutoRotate(!autoRotate));
    viewer.querySelectorAll('[data-zoom]').forEach((button) => button.addEventListener('click', () => zoomTo(zoom + (button.dataset.zoom === 'in' ? 0.2 : -0.2))));
    viewer.querySelector('[data-fullscreen]').addEventListener('click', async () => {
      try {
        if (document.fullscreenElement) await document.exitFullscreen();
        else if (stage.requestFullscreen) await stage.requestFullscreen();
        else stage.classList.toggle('viewer-fullscreen-fallback');
      } catch (_error) {
        stage.classList.toggle('viewer-fullscreen-fallback');
      }
    });

    canvas.addEventListener('pointerdown', (event) => {
      activePointers.set(event.pointerId, { x: event.clientX, y: event.clientY });
      canvas.setPointerCapture(event.pointerId);
      if (activePointers.size === 2) {
        const points = [...activePointers.values()];
        pinchDistance = Math.hypot(points[0].x - points[1].x, points[0].y - points[1].y);
        dragging = false;
        return;
      }
      if (activePointers.size !== 1) return;
      markInteracted();
      pointerId = event.pointerId;
      lastX = event.clientX;
      lastMoveAt = performance.now();
      dragging = true;
      velocity = 0;
      resumeAutoAfterDrag = autoRotate;
      if (autoRotate) setAutoRotate(false);
      window.clearTimeout(resumeTimer);
      canvas.classList.add('is-dragging');
    });

    canvas.addEventListener('pointermove', (event) => {
      if (!activePointers.has(event.pointerId)) return;
      activePointers.set(event.pointerId, { x: event.clientX, y: event.clientY });
      if (activePointers.size >= 2) {
        const points = [...activePointers.values()];
        const nextDistance = Math.hypot(points[0].x - points[1].x, points[0].y - points[1].y);
        if (pinchDistance) zoomTo(zoom * (nextDistance / pinchDistance));
        pinchDistance = nextDistance;
        return;
      }
      if (!dragging || event.pointerId !== pointerId) return;
      const now = performance.now();
      const deltaX = event.clientX - lastX;
      const elapsed = Math.max(1, now - lastMoveAt);
      const frameDelta = -deltaX / ROTATION_SENSITIVITY;
      position += frameDelta;
      velocity = Math.max(-0.06, Math.min(0.06, frameDelta / elapsed));
      lastX = event.clientX;
      lastMoveAt = now;
      requestDraw();
    });

    function finishPointer(event) {
      activePointers.delete(event.pointerId);
      if (event.pointerId !== pointerId) return;
      dragging = false;
      pointerId = null;
      canvas.classList.remove('is-dragging');
      requestDraw();
      if (resumeAutoAfterDrag) {
        resumeTimer = window.setTimeout(() => setAutoRotate(true), 2600);
        resumeAutoAfterDrag = false;
      }
    }
    canvas.addEventListener('pointerup', finishPointer);
    canvas.addEventListener('pointercancel', finishPointer);
    canvas.addEventListener('lostpointercapture', finishPointer);

    canvas.addEventListener('wheel', (event) => {
      event.preventDefault();
      zoomTo(zoom + (event.deltaY < 0 ? 0.12 : -0.12));
    }, { passive: false });
    canvas.addEventListener('keydown', (event) => {
      if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
        event.preventDefault();
        markInteracted();
        position += event.key === 'ArrowLeft' ? -1 : 1;
        requestDraw();
      } else if (event.code === 'Space') {
        event.preventDefault();
        setAutoRotate(!autoRotate);
      }
    });
    document.addEventListener('visibilitychange', () => {
      if (document.hidden) stopAnimation();
      else if (autoRotate || velocity) requestDraw();
    });
    window.addEventListener('pagehide', () => {
      stopAnimation();
      window.clearTimeout(resumeTimer);
    }, { once: true });
  });
})();
