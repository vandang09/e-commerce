import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { DRACOLoader } from 'three/addons/loaders/DRACOLoader.js';

const DEFAULT_QUALITY = 'auto';
const QUALITY_SETTINGS = {
  low: { pixelRatio: 1, shadows: false, shadowSize: 512 },
  medium: { pixelRatio: 1.35, shadows: true, shadowSize: 1024 },
  high: { pixelRatio: 1.75, shadows: true, shadowSize: 1536 },
};
const DRACO_DECODER_PATH = 'https://www.gstatic.com/draco/versioned/decoders/1.5.6/';

class Product3DViewer {
  constructor(root) {
    this.root = root;
    this.data = JSON.parse(root.querySelector('[data-3d-model-data]').textContent);
    this.stage = root.querySelector('[data-three-stage]');
    this.canvas = root.querySelector('[data-three-canvas]');
    this.loading = root.querySelector('[data-three-loading]');
    this.errorPanel = root.querySelector('[data-three-error]');
    this.quality = DEFAULT_QUALITY;
    this.autoRotateBeforeInput = false;
    this.isVisible = false;
    this.isReady = false;
    this.isDestroyed = false;
    this.animationFrame = 0;
    this.resizeObserver = null;
    this.modelRoot = null;
    this.mixer = null;
    this.clock = new THREE.Clock();
    this.resourceSet = { geometries: new Set(), materials: new Set(), textures: new Set() };
    this.onResize = this.resize.bind(this);
    this.onKeyDown = this.handleKeyDown.bind(this);
    this.onVisibilityChange = this.handleVisibilityChange.bind(this);
    this.onFullscreenChange = this.handleFullscreenChange.bind(this);
    this.bindViewModes();
    this.bindToolbar();
    this.bindSettings();
    this.observeStage();
    window.addEventListener('pagehide', () => this.destroy(), { once: true });
    document.addEventListener('visibilitychange', this.onVisibilityChange);
    document.addEventListener('fullscreenchange', this.onFullscreenChange);
  }

  bindViewModes() {
    this.root.querySelectorAll('[data-view-mode]').forEach((button) => {
      button.addEventListener('click', () => this.setMode(button.dataset.viewMode));
    });
    this.root.querySelector('[data-error-photos]').addEventListener('click', () => this.setMode('image'));
  }

  setMode(mode) {
    this.root.querySelectorAll('[data-view-panel]').forEach((panel) => {
      panel.hidden = panel.dataset.viewPanel !== mode;
    });
    this.root.querySelectorAll('[data-view-mode]').forEach((button) => {
      const selected = button.dataset.viewMode === mode;
      button.classList.toggle('is-active', selected);
      button.setAttribute('aria-selected', String(selected));
    });
    if (mode === 'three') {
      this.resize();
      this.startRendering();
      this.canvas.focus({ preventScroll: true });
    } else {
      this.stopRendering();
    }
  }

  observeStage() {
    if ('IntersectionObserver' in window) {
      this.visibilityObserver = new IntersectionObserver((entries) => {
        const entry = entries[0];
        this.isVisible = entry.isIntersecting;
        if (this.isVisible) this.initialize();
        else this.stopRendering();
      }, { rootMargin: '160px', threshold: 0.01 });
      this.visibilityObserver.observe(this.stage);
    } else {
      this.isVisible = true;
      this.initialize();
    }
  }

  initialize() {
    if (this.renderer || this.isDestroyed) {
      this.startRendering();
      return;
    }
    try {
      this.createScene();
      this.loadModel();
      this.resizeObserver = new ResizeObserver(this.onResize);
      this.resizeObserver.observe(this.stage);
      window.addEventListener('resize', this.onResize, { passive: true });
      this.canvas.addEventListener('keydown', this.onKeyDown);
      this.startRendering();
    } catch (error) {
      console.error('Unable to initialize the Three.js product viewer.', error);
      this.showError('Your browser could not start WebGL. View the product photos instead.');
    }
  }

  createScene() {
    this.scene = new THREE.Scene();
    this.camera = new THREE.PerspectiveCamera(35, 1, 0.01, 10000);
    this.renderer = new THREE.WebGLRenderer({
      canvas: this.canvas,
      antialias: true,
      alpha: true,
      powerPreference: 'high-performance',
      preserveDrawingBuffer: false,
    });
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    this.renderer.toneMappingExposure = 1.12;
    this.renderer.setClearColor(0x000000, 0);
    this.renderer.shadowMap.enabled = false;
    this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;

    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.enableDamping = true;
    this.controls.dampingFactor = 0.075;
    this.controls.enablePan = true;
    this.controls.rotateSpeed = 0.72;
    this.controls.zoomSpeed = 0.8;
    this.controls.panSpeed = 0.62;
    this.controls.minPolarAngle = 0.08;
    this.controls.maxPolarAngle = Math.PI - 0.08;
    this.controls.autoRotateSpeed = 0.52;
    this.controls.addEventListener('start', () => this.pauseAutoForInput());
    this.controls.addEventListener('end', () => this.resumeAutoAfterInput());

    this.hemisphereLight = new THREE.HemisphereLight(0xf7f2e9, 0x46544c, 2.0);
    this.scene.add(this.hemisphereLight);
    this.keyLight = new THREE.DirectionalLight(0xfff4e7, 3.0);
    this.keyLight.position.set(4, 7, 6);
    this.scene.add(this.keyLight);
    this.fillLight = new THREE.DirectionalLight(0xd7e5ff, 1.35);
    this.fillLight.position.set(-5, 3, 4);
    this.scene.add(this.fillLight);
    this.rimLight = new THREE.DirectionalLight(0xffffff, 2.2);
    this.rimLight.position.set(-2, 5, -6);
    this.scene.add(this.rimLight);

    this.ground = new THREE.Mesh(
      new THREE.PlaneGeometry(1, 1),
      new THREE.ShadowMaterial({ color: 0x26372f, opacity: 0.13 }),
    );
    this.ground.rotation.x = -Math.PI / 2;
    this.ground.receiveShadow = true;
    this.ground.visible = false;
    this.scene.add(this.ground);
    this.applyQuality(DEFAULT_QUALITY);
    this.renderer.domElement.addEventListener('webglcontextlost', (event) => {
      event.preventDefault();
      this.stopRendering();
      this.showError('The 3D graphics context was interrupted. Reload the page or view product photos.');
    });
  }

  loadModel() {
    const loadingText = this.root.querySelector('[data-three-loading-text]');
    const progress = this.root.querySelector('[data-three-progress]');
    const progressLabel = this.root.querySelector('[data-three-progress-label]');
    const dracoLoader = new DRACOLoader();
    dracoLoader.setDecoderPath(DRACO_DECODER_PATH);
    const loader = new GLTFLoader();
    loader.setDRACOLoader(dracoLoader);
    loader.load(this.data.url, (gltf) => {
      if (this.isDestroyed) return;
      this.setupModel(gltf);
      this.loading.classList.add('is-complete');
      window.setTimeout(() => { if (!this.isDestroyed) this.loading.hidden = true; }, 280);
    }, (event) => {
      if (event.total > 0) {
        const percent = Math.min(100, Math.round((event.loaded / event.total) * 100));
        progress.value = percent;
        progressLabel.textContent = `${percent}%`;
      } else {
        loadingText.textContent = 'Loading 3D model…';
      }
    }, (error) => {
      console.error(`Failed to load product model: ${this.data.url}`, error);
      this.showError('This model could not be loaded. The product photos are still available.');
      dracoLoader.dispose();
    });
    this.dracoLoader = dracoLoader;
  }

  setupModel(gltf) {
    const source = gltf.scene;
    const bounds = new THREE.Box3().setFromObject(source);
    const size = bounds.getSize(new THREE.Vector3());
    const center = bounds.getCenter(new THREE.Vector3());
    const maxDimension = Math.max(size.x, size.y, size.z);
    if (!Number.isFinite(maxDimension) || maxDimension <= 0) {
      this.showError('This model has no visible geometry. View the product photos instead.');
      return;
    }

    this.modelRoot = new THREE.Group();
    source.position.sub(center);
    this.modelRoot.add(source);
    this.scene.add(this.modelRoot);
    source.traverse((object) => {
      if (!object.isMesh) return;
      object.castShadow = true;
      object.receiveShadow = true;
      if (object.geometry) this.resourceSet.geometries.add(object.geometry);
      const materials = Array.isArray(object.material) ? object.material : [object.material];
      materials.filter(Boolean).forEach((material) => {
        this.resourceSet.materials.add(material);
        Object.values(material).forEach((value) => {
          if (value?.isTexture) this.resourceSet.textures.add(value);
        });
      });
    });

    const verticalFov = THREE.MathUtils.degToRad(this.camera.fov);
    const fitDistance = (maxDimension * 0.5) / Math.tan(verticalFov * 0.5) * 1.55;
    this.camera.position.set(fitDistance * 0.72, fitDistance * 0.48, fitDistance);
    this.camera.near = Math.max(0.001, maxDimension / 1000);
    this.camera.far = Math.max(100, maxDimension * 30);
    this.camera.updateProjectionMatrix();
    this.controls.target.set(0, 0, 0);
    this.controls.minDistance = fitDistance * 0.45;
    this.controls.maxDistance = fitDistance * 3.25;
    this.controls.update();
    this.defaultCameraPosition = this.camera.position.clone();
    this.defaultTarget = this.controls.target.clone();

    this.ground.geometry.dispose();
    this.ground.geometry = new THREE.PlaneGeometry(maxDimension * 5, maxDimension * 5);
    this.ground.position.y = -size.y * 0.5 - maxDimension * 0.015;
    this.ground.visible = this.renderer.shadowMap.enabled;
    this.modelRoot.scale.setScalar(0.92);
    this.introStartedAt = performance.now();
    this.introDuration = 520;
    if (gltf.animations?.length) {
      this.mixer = new THREE.AnimationMixer(source);
      gltf.animations.forEach((clip) => this.mixer.clipAction(clip).play());
    }
    this.isReady = true;
    this.resize();
    this.startRendering();
  }

  bindToolbar() {
    this.root.querySelector('[data-three-reset]').addEventListener('click', () => this.resetCamera());
    this.root.querySelector('[data-three-auto]').addEventListener('click', () => {
      this.controls.autoRotate = !this.controls.autoRotate;
      this.setAutoButtonState(this.controls.autoRotate);
      this.startRendering();
    });
    this.root.querySelector('[data-three-fullscreen]').addEventListener('click', () => this.toggleFullscreen());
    const settingsButton = this.root.querySelector('[data-three-settings]');
    const settingsPanel = this.root.querySelector('[data-three-settings-panel]');
    settingsButton.addEventListener('click', () => {
      settingsPanel.hidden = !settingsPanel.hidden;
      settingsButton.setAttribute('aria-expanded', String(!settingsPanel.hidden));
    });
    this.root.querySelector('[data-error-photos]').addEventListener('click', () => this.setMode('image'));
  }

  bindSettings() {
    this.root.querySelector('[data-three-quality]').addEventListener('change', (event) => this.applyQuality(event.target.value));
    this.root.querySelector('[data-three-shadows]').addEventListener('change', (event) => {
      this.renderer.shadowMap.enabled = event.target.checked && this.quality !== 'low';
      this.keyLight.castShadow = this.renderer.shadowMap.enabled;
      this.ground.visible = this.renderer.shadowMap.enabled;
    });
    this.root.querySelector('[data-three-lighting]').addEventListener('change', (event) => {
      const daylight = event.target.value === 'daylight';
      this.hemisphereLight.intensity = daylight ? 2.35 : 1.65;
      this.keyLight.intensity = daylight ? 2.45 : 3.0;
      this.fillLight.intensity = daylight ? 1.8 : 1.35;
      this.rimLight.intensity = daylight ? 1.5 : 2.2;
      this.stage.classList.toggle('three-stage-daylight', daylight);
      this.startRendering();
    });
  }

  applyQuality(choice) {
    const autoQuality = window.matchMedia('(max-width: 760px)').matches || (navigator.deviceMemory && navigator.deviceMemory <= 4) ? 'low' : 'medium';
    const selected = choice === 'auto' ? autoQuality : choice;
    const settings = QUALITY_SETTINGS[selected] || QUALITY_SETTINGS.medium;
    this.quality = selected;
    if (!this.renderer) return;
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, settings.pixelRatio, 1.75));
    this.renderer.shadowMap.enabled = settings.shadows;
    this.keyLight.castShadow = settings.shadows;
    this.keyLight.shadow.mapSize.set(settings.shadowSize, settings.shadowSize);
    this.ground.visible = settings.shadows;
    this.resize();
    this.startRendering();
  }

  pauseAutoForInput() {
    this.autoRotateBeforeInput = this.controls.autoRotate;
    if (this.autoRotateBeforeInput) {
      this.controls.autoRotate = false;
      this.setAutoButtonState(false);
    }
    window.clearTimeout(this.resumeAutoTimer);
    this.root.querySelector('[data-three-hint]').classList.add('is-dismissed');
  }

  resumeAutoAfterInput() {
    if (!this.autoRotateBeforeInput) return;
    this.resumeAutoTimer = window.setTimeout(() => {
      if (this.isDestroyed) return;
      this.controls.autoRotate = true;
      this.setAutoButtonState(true);
      this.startRendering();
    }, 2400);
    this.autoRotateBeforeInput = false;
  }

  setAutoButtonState(active) {
    const button = this.root.querySelector('[data-three-auto]');
    button.setAttribute('aria-pressed', String(active));
    button.setAttribute('aria-label', active ? 'Pause automatic rotation' : 'Start automatic rotation');
    button.querySelector('span').textContent = active ? 'Pause' : 'Auto';
    button.firstChild.textContent = active ? 'Ⅱ ' : '▶ ';
  }

  handleKeyDown(event) {
    if (event.key === ' ' || event.code === 'Space') {
      event.preventDefault();
      this.root.querySelector('[data-three-auto]').click();
      return;
    }
    if (!['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'].includes(event.key)) return;
    event.preventDefault();
    const offset = this.camera.position.clone().sub(this.controls.target);
    const spherical = new THREE.Spherical().setFromVector3(offset);
    const step = THREE.MathUtils.degToRad(5);
    if (event.key === 'ArrowLeft') spherical.theta -= step;
    if (event.key === 'ArrowRight') spherical.theta += step;
    if (event.key === 'ArrowUp') spherical.phi = Math.max(0.08, spherical.phi - step);
    if (event.key === 'ArrowDown') spherical.phi = Math.min(Math.PI - 0.08, spherical.phi + step);
    this.camera.position.copy(this.controls.target).add(new THREE.Vector3().setFromSpherical(spherical));
    this.controls.update();
    this.root.querySelector('[data-three-hint]').classList.add('is-dismissed');
    this.startRendering();
  }

  resetCamera() {
    if (!this.defaultCameraPosition) return;
    this.resetAnimation = {
      fromPosition: this.camera.position.clone(),
      fromTarget: this.controls.target.clone(),
      startedAt: performance.now(),
      duration: 420,
    };
    this.startRendering();
  }

  applyResetAnimation(now) {
    if (!this.resetAnimation) return;
    const animation = this.resetAnimation;
    const progress = Math.min(1, (now - animation.startedAt) / animation.duration);
    const eased = 1 - Math.pow(1 - progress, 3);
    this.camera.position.lerpVectors(animation.fromPosition, this.defaultCameraPosition, eased);
    this.controls.target.lerpVectors(animation.fromTarget, this.defaultTarget, eased);
    if (progress >= 1) this.resetAnimation = null;
  }

  async toggleFullscreen() {
    try {
      if (document.fullscreenElement) await document.exitFullscreen();
      else if (this.stage.requestFullscreen) await this.stage.requestFullscreen();
      else this.stage.classList.toggle('three-stage-fullscreen-fallback');
    } catch (error) {
      console.warn('Fullscreen is not available in this browser.', error);
      this.stage.classList.toggle('three-stage-fullscreen-fallback');
    }
    this.resize();
  }

  handleFullscreenChange() {
    const button = this.root.querySelector('[data-three-fullscreen]');
    const active = document.fullscreenElement === this.stage;
    button.setAttribute('aria-label', active ? 'Exit fullscreen' : 'Enter fullscreen');
    button.querySelector('span').textContent = active ? 'Exit' : 'Full';
    requestAnimationFrame(() => this.resize());
  }

  resize() {
    if (!this.renderer || !this.camera || this.isDestroyed) return;
    const bounds = this.stage.getBoundingClientRect();
    if (bounds.width < 1 || bounds.height < 1) return;
    this.camera.aspect = bounds.width / bounds.height;
    this.camera.updateProjectionMatrix();
    this.renderer.setSize(bounds.width, bounds.height, false);
  }

  startRendering() {
    if (!this.isVisible || document.hidden || this.isDestroyed || !this.renderer || this.animationFrame) return;
    const render = (now) => {
      this.animationFrame = 0;
      if (!this.isVisible || document.hidden || this.isDestroyed) return;
      const delta = Math.min(this.clock.getDelta(), 0.05);
      const controlsChanged = this.controls.update();
      this.mixer?.update(delta);
      if (this.modelRoot && this.introStartedAt) {
        const progress = Math.min(1, (now - this.introStartedAt) / this.introDuration);
        const eased = 1 - Math.pow(1 - progress, 3);
        this.modelRoot.scale.setScalar(0.92 + eased * 0.08);
        if (progress >= 1) this.introStartedAt = 0;
      }
      this.applyResetAnimation(now);
      this.renderer.render(this.scene, this.camera);
      const introActive = Boolean(this.introStartedAt);
      if (this.controls.autoRotate || this.mixer || this.resetAnimation || introActive || controlsChanged) {
        this.animationFrame = requestAnimationFrame(render);
      }
    };
    this.animationFrame = requestAnimationFrame(render);
  }

  stopRendering() {
    if (this.animationFrame) cancelAnimationFrame(this.animationFrame);
    this.animationFrame = 0;
    this.clock.stop();
  }

  handleVisibilityChange() {
    if (document.hidden) this.stopRendering();
    else if (this.isVisible) {
      this.clock.start();
      this.startRendering();
    }
  }

  showError(message) {
    this.loading.hidden = true;
    this.errorPanel.hidden = false;
    this.root.querySelector('[data-three-error-text]').textContent = message;
    this.stopRendering();
  }

  destroy() {
    if (this.isDestroyed) return;
    this.isDestroyed = true;
    this.stopRendering();
    this.visibilityObserver?.disconnect();
    this.resizeObserver?.disconnect();
    window.removeEventListener('resize', this.onResize);
    document.removeEventListener('visibilitychange', this.onVisibilityChange);
    document.removeEventListener('fullscreenchange', this.onFullscreenChange);
    this.canvas.removeEventListener('keydown', this.onKeyDown);
    window.clearTimeout(this.resumeAutoTimer);
    this.controls?.dispose();
    this.mixer?.stopAllAction();
    this.resourceSet.geometries.forEach((geometry) => geometry.dispose());
    this.resourceSet.materials.forEach((material) => material.dispose());
    this.resourceSet.textures.forEach((texture) => texture.dispose());
    this.dracoLoader?.dispose();
    this.renderer?.dispose();
    this.renderer?.forceContextLoss();
  }
}

const initializeViewer = async (root) => {
  try {
    const viewer = new Product3DViewer(root);
    if (!('IntersectionObserver' in window)) viewer.initialize();
  } catch (error) {
    console.error('Unable to create the Three.js product viewer.', error);
    const loading = root.querySelector('[data-three-loading]');
    const errorPanel = root.querySelector('[data-three-error]');
    loading.hidden = true;
    errorPanel.hidden = false;
    root.querySelector('[data-three-error-text]').textContent = 'WebGL could not start. View the product photos instead.';
  }
};

document.querySelectorAll('.product-viewer-3d').forEach(initializeViewer);
