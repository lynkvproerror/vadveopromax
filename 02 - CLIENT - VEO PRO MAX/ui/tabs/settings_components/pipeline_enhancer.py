"""
Pipeline & Enhancer mixin — pipeline optimization settings and
image enhancer (GPU status, model download, toggle states).

Extracted from tab_settings.py.  All methods operate on shared `self`
attributes initialised by TabSettings.__init__.
"""

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton,
    QFrame, QComboBox, QSpinBox, QDoubleSpinBox,
)
from ui.popups import show_info, show_warning, show_confirm
from PySide6.QtCore import QTimer

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from config.theme import Theme


class SettingsPipelineEnhancerMixin:
    """Pipeline optimization + Image enhancer sections."""

    def _create_pipeline_section(self) -> QWidget:
        """Create Pipeline Optimization section with live-tunable settings."""
        section, layout = self._create_section("🔧 Pipeline Optimization")

        # Load current values from AppSettings (persisted) + controller (runtime)
        from config.settings import get_settings as _gs
        _s = _gs()
        ps = {
            'adaptive_burst_enabled': getattr(_s, 'adaptive_burst_enabled', True),
            'burst_min_delay': getattr(_s, 'burst_min_delay', 2.0),
            'burst_max_delay': getattr(_s, 'burst_max_delay', 15.0),
            'recaptcha_pool_enabled': getattr(_s, 'recaptcha_pool_enabled', True),
            'pool_size': getattr(_s, 'recaptcha_pool_size', 2),
            'watchdog_timeout_min': getattr(_s, 'watchdog_timeout_min', 10),
            'journal_save_interval_sec': getattr(_s, 'journal_save_interval_sec', 30),
            'workload_priority': getattr(_s, 'workload_priority', 'prompts_first'),
        }

        def _update(key):
            """Factory for pipeline settings callback — live-update + persist."""
            def _cb(value):
                if self.controller and hasattr(self.controller, 'update_pipeline_settings'):
                    self.controller.update_pipeline_settings(key, value)
                self._save_pipeline_settings()
            return _cb

        # --- Adaptive Burst ---
        self.burst_switch = self._create_enable_row(
            "⚡ Adaptive Burst:", checked=ps.get('adaptive_burst_enabled', True),
            bold=True, color=Theme.BLUE
        )
        layout.addLayout(self.burst_switch._row_layout)

        burst_container = QWidget()
        burst_layout = QVBoxLayout(burst_container)
        burst_layout.setContentsMargins(0, 0, 0, 0)

        # Burst Min Delay
        bmin_row = QHBoxLayout()
        bmin_label = QLabel("Min Delay:")
        bmin_label.setFixedWidth(150)
        bmin_label.setStyleSheet(f"color: {Theme.TEXT};")
        bmin_row.addWidget(bmin_label)
        self.burst_min = QDoubleSpinBox()
        self.burst_min.setRange(0.5, 10.0)
        self.burst_min.setSingleStep(0.5)
        self.burst_min.setDecimals(1)
        self.burst_min.setValue(ps.get('burst_min_delay', 2.0))
        self.burst_min.setFixedWidth(100)
        self.burst_min.setSuffix("s")
        self.burst_min.valueChanged.connect(_update('burst_min_delay'))
        bmin_row.addWidget(self.burst_min)
        bmin_row.addStretch()
        burst_layout.addLayout(bmin_row)

        # Burst Max Delay
        bmax_row = QHBoxLayout()
        bmax_label = QLabel("Max Delay:")
        bmax_label.setFixedWidth(150)
        bmax_label.setStyleSheet(f"color: {Theme.TEXT};")
        bmax_row.addWidget(bmax_label)
        self.burst_max = QDoubleSpinBox()
        self.burst_max.setRange(5.0, 60.0)
        self.burst_max.setSingleStep(1.0)
        self.burst_max.setDecimals(1)
        self.burst_max.setValue(ps.get('burst_max_delay', 15.0))
        self.burst_max.setFixedWidth(100)
        self.burst_max.setSuffix("s")
        self.burst_max.valueChanged.connect(_update('burst_max_delay'))
        bmax_row.addWidget(self.burst_max)
        bmax_row.addStretch()
        burst_layout.addLayout(bmax_row)

        layout.addWidget(burst_container)
        burst_container.setVisible(self.burst_switch.isToggled())
        self.burst_switch.toggled_signal.connect(burst_container.setVisible)
        self.burst_switch.toggled_signal.connect(_update('adaptive_burst_enabled'))
        # Cross-validation: burst min ≤ max (M3 fix)
        self.burst_min.valueChanged.connect(self._clamp_burst_delays)
        self.burst_max.valueChanged.connect(self._clamp_burst_delays)

        # --- reCAPTCHA Pool ---
        self.pool_switch = self._create_enable_row(
            "🔄 reCAPTCHA Pool:", checked=ps.get('recaptcha_pool_enabled', True),
            bold=True, color=Theme.GREEN
        )
        self.pool_switch.toggled_signal.connect(_update('recaptcha_pool_enabled'))
        layout.addLayout(self.pool_switch._row_layout)

        pool_row = QHBoxLayout()
        pool_label = QLabel("Pool Size:")
        pool_label.setFixedWidth(150)
        pool_label.setStyleSheet(f"color: {Theme.TEXT};")
        pool_row.addWidget(pool_label)
        self.pool_size = QSpinBox()
        self.pool_size.setRange(1, 5)
        self.pool_size.setValue(ps.get('pool_size', 2))
        self.pool_size.setFixedWidth(100)
        self.pool_size.valueChanged.connect(_update('pool_size'))
        pool_row.addWidget(self.pool_size)
        pool_row.addStretch()
        layout.addLayout(pool_row)

        # --- Watchdog ---
        wd_row = QHBoxLayout()
        wd_label = QLabel("🐕 Watchdog Timeout:")
        wd_label.setFixedWidth(150)
        wd_label.setStyleSheet(f"color: {Theme.TEXT}; font-weight: bold;")
        wd_row.addWidget(wd_label)
        self.watchdog_timeout = QSpinBox()
        self.watchdog_timeout.setRange(5, 60)
        self.watchdog_timeout.setValue(ps.get('watchdog_timeout_min', 10))
        self.watchdog_timeout.setFixedWidth(100)
        self.watchdog_timeout.setSuffix(" min")
        self.watchdog_timeout.valueChanged.connect(_update('watchdog_timeout_min'))
        wd_row.addWidget(self.watchdog_timeout)
        wd_row.addStretch()
        layout.addLayout(wd_row)

        # --- Journal ---
        jr_row = QHBoxLayout()
        jr_label = QLabel("📓 Journal Auto-save:")
        jr_label.setFixedWidth(150)
        jr_label.setStyleSheet(f"color: {Theme.TEXT}; font-weight: bold;")
        jr_row.addWidget(jr_label)
        self.journal_interval = QSpinBox()
        self.journal_interval.setRange(10, 120)
        self.journal_interval.setValue(ps.get('journal_save_interval_sec', 30))
        self.journal_interval.setFixedWidth(100)
        self.journal_interval.setSuffix("s")
        self.journal_interval.valueChanged.connect(_update('journal_save_interval_sec'))
        jr_row.addWidget(self.journal_interval)
        jr_row.addStretch()
        layout.addLayout(jr_row)

        # --- Workload Priority ---
        wp_row = QHBoxLayout()
        wp_label = QLabel("⚡ Workload Priority:")
        wp_label.setFixedWidth(150)
        wp_label.setStyleSheet(f"color: {Theme.TEXT}; font-weight: bold;")
        wp_row.addWidget(wp_label)
        self.workload_priority = QComboBox()
        self.workload_priority.addItems([
            "⚖️ Balanced",
            "📝 Prompts First",
            "⬆️ Upscale First"
        ])
        self.workload_priority.setFixedWidth(160)
        # Map display names to engine values
        self._wp_map = {0: 'balanced', 1: 'prompts_first', 2: 'upscale_first'}
        current_wp = ps.get('workload_priority', 'prompts_first')
        reverse_map = {v: k for k, v in self._wp_map.items()}
        self.workload_priority.setCurrentIndex(reverse_map.get(current_wp, 0))
        self.workload_priority.currentIndexChanged.connect(
            lambda idx: _update('workload_priority')(self._wp_map.get(idx, 'balanced'))
        )
        wp_row.addWidget(self.workload_priority)
        wp_hint = QLabel("Controls resource allocation")
        wp_hint.setStyleSheet(f"color: {Theme.SUBTEXT0}; font-size: 10px; margin-left: 8px;")
        wp_row.addWidget(wp_hint)
        wp_row.addStretch()
        layout.addLayout(wp_row)

        return section

    def _clamp_burst_delays(self, *args):
        """Ensure burst_min ≤ burst_max by auto-clamping."""
        if getattr(self, '_initializing', False):
            return
        mn = self.burst_min.value()
        mx = self.burst_max.value()
        if mn > mx:
            self.burst_max.blockSignals(True)
            self.burst_max.setValue(mn)
            self.burst_max.blockSignals(False)

    def _save_pipeline_settings(self, *args):
        """Persist all pipeline optimization settings to AppSettings."""
        if getattr(self, '_initializing', False):
            return
        try:
            from config.settings import get_settings, save_settings
            import logging
            settings = get_settings()
            settings.adaptive_burst_enabled = self.burst_switch.isToggled()
            settings.burst_min_delay = self.burst_min.value()
            settings.burst_max_delay = self.burst_max.value()
            settings.recaptcha_pool_enabled = self.pool_switch.isToggled()
            settings.recaptcha_pool_size = self.pool_size.value()
            settings.watchdog_timeout_min = self.watchdog_timeout.value()
            settings.journal_save_interval_sec = self.journal_interval.value()
            settings.workload_priority = self._wp_map.get(
                self.workload_priority.currentIndex(), 'prompts_first'
            )
            save_settings()
        except Exception as e:
            logging.getLogger('settings').error(f'Failed to save pipeline settings: {e}')

    def _create_enhancer_section(self) -> QWidget:
        """Create Image Enhancer section — GPU status, 3 toggles, model download."""
        section, layout = self._create_section("✨ Image Enhancer (AI Upscale)")

        # GPU Status row
        gpu_row = QHBoxLayout()
        gpu_label = QLabel("GPU Status:")
        gpu_label.setFixedWidth(150)
        gpu_label.setStyleSheet(f"color: {Theme.TEXT}; font-weight: bold;")
        gpu_row.addWidget(gpu_label)

        self._enhance_gpu_status = QLabel("🔍 Detecting GPU...")
        self._enhance_gpu_status.setStyleSheet(f"color: {Theme.SUBTEXT0};")
        gpu_row.addWidget(self._enhance_gpu_status)
        gpu_row.addStretch()
        layout.addLayout(gpu_row)

        # Model Status row
        model_row = QHBoxLayout()
        model_label = QLabel("AI Models:")
        model_label.setFixedWidth(150)
        model_label.setStyleSheet(f"color: {Theme.TEXT}; font-weight: bold;")
        model_row.addWidget(model_label)

        self._enhance_model_status = QLabel("⏳ Checking...")
        self._enhance_model_status.setStyleSheet(f"color: {Theme.SUBTEXT0};")
        model_row.addWidget(self._enhance_model_status)

        self._enhance_download_btn = QPushButton("⬇️ Download Models")
        self._enhance_download_btn.setFixedHeight(28)
        self._enhance_download_btn.setStyleSheet(
            f"background-color: {Theme.BLUE}; font-size: 11px; padding: 2px 12px;"
        )
        self._enhance_download_btn.clicked.connect(self._on_download_enhancer_models)
        self._enhance_download_btn.setVisible(False)  # Show only when models missing
        model_row.addWidget(self._enhance_download_btn)
        model_row.addStretch()
        layout.addLayout(model_row)

        # Download progress bar (hidden by default)
        self._enhance_progress = None
        try:
            from PySide6.QtWidgets import QProgressBar
            self._enhance_progress = QProgressBar()
            self._enhance_progress.setFixedHeight(18)
            self._enhance_progress.setRange(0, 100)
            self._enhance_progress.setVisible(False)
            self._enhance_progress.setStyleSheet(f"""
                QProgressBar {{
                    background-color: {Theme.SURFACE2};
                    border-radius: 4px;
                    text-align: center;
                    font-size: 10px;
                    color: {Theme.TEXT};
                }}
                QProgressBar::chunk {{
                    background-color: {Theme.GREEN};
                    border-radius: 4px;
                }}
            """)
            layout.addWidget(self._enhance_progress)
        except Exception:
            pass

        # Separator
        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background-color: {Theme.OVERLAY0};")
        layout.addWidget(sep)

        # Load saved toggle states from AppSettings
        _ctx_on = True
        _lib_on = True
        _auto_on = False
        try:
            from config.settings import get_settings as _gs
            _s = _gs()
            _ctx_on = getattr(_s, 'enhance_context_menu', True)
            _lib_on = getattr(_s, 'enhance_library', True)
            _auto_on = getattr(_s, 'enhance_auto_continuation', False)
        except Exception:
            pass

        # Toggle 1: Context Menu Enhance
        self._enhance_context_toggle = self._create_enable_row(
            "Context Menu", checked=_ctx_on, badge=""
        )
        self._enhance_context_toggle.setToolTip(
            "Right-click on images to enhance them (upscale/face restore)"
        )
        layout.addLayout(self._enhance_context_toggle._row_layout)

        # Toggle 2: Library Enhance
        self._enhance_library_toggle = self._create_enable_row(
            "Library Enhance", checked=_lib_on, badge=""
        )
        self._enhance_library_toggle.setToolTip(
            "Add 'Enhance' button to Image Library toolbar"
        )
        layout.addLayout(self._enhance_library_toggle._row_layout)

        # Toggle 3: Auto-Enhance Continuation Frames
        self._enhance_auto_toggle = self._create_enable_row(
            "Auto-Enhance", checked=_auto_on, badge="BETA"
        )
        self._enhance_auto_toggle.setToolTip(
            "Automatically enhance continuation frames before uploading (may add 5-10s per chain)"
        )
        layout.addLayout(self._enhance_auto_toggle._row_layout)

        # Connect toggles to save
        self._enhance_context_toggle.toggled_signal.connect(self._save_enhancer_settings)
        self._enhance_library_toggle.toggled_signal.connect(self._save_enhancer_settings)
        self._enhance_auto_toggle.toggled_signal.connect(self._save_enhancer_settings)

        # PyTorch install button (shown only if torch not installed)
        self._enhance_install_btn = QPushButton("📦 Install PyTorch (CUDA)")
        self._enhance_install_btn.setFixedHeight(28)
        self._enhance_install_btn.setStyleSheet(
            f"background-color: {Theme.YELLOW}; color: {Theme.BASE}; "
            f"font-size: 11px; font-weight: bold; padding: 2px 12px;"
        )
        self._enhance_install_btn.clicked.connect(self._on_install_pytorch)
        self._enhance_install_btn.setVisible(False)
        layout.addWidget(self._enhance_install_btn)

        # Start GPU detection refresh (poll GPUDetector result)
        self._enhance_check_timer = QTimer(self)
        self._enhance_check_timer.timeout.connect(self._refresh_enhancer_status)
        self._enhance_check_timer.start(2000)  # Check every 2s until resolved

        return section

    def _refresh_enhancer_status(self):
        """Detect GPU and model status directly — no controller dependency."""
        import logging
        log = logging.getLogger("enhancer")

        # ── GPU Detection (try import torch) ──
        try:
            import torch
            if torch.cuda.is_available():
                gpu_name = torch.cuda.get_device_name(0)
                vram = torch.cuda.get_device_properties(0).total_mem // (1024**3)
                self._enhance_gpu_status.setText(f"✅ {gpu_name} ({vram}GB VRAM)")
                self._enhance_gpu_status.setStyleSheet(f"color: {Theme.GREEN};")
                self._enhance_install_btn.setVisible(False)
            else:
                self._enhance_gpu_status.setText("⚠️ PyTorch installed but no CUDA GPU detected")
                self._enhance_gpu_status.setStyleSheet(f"color: {Theme.YELLOW};")
                self._enhance_install_btn.setVisible(False)
                # Disable toggles — CPU mode too slow for real-time
                self._enhance_context_toggle.setEnabled(False)
                self._enhance_library_toggle.setEnabled(False)
                self._enhance_auto_toggle.setEnabled(False)
        except ImportError:
            self._enhance_gpu_status.setText("❌ PyTorch not installed")
            self._enhance_gpu_status.setStyleSheet(f"color: {Theme.RED};")
            self._enhance_install_btn.setVisible(True)
            self._enhance_context_toggle.setEnabled(False)
            self._enhance_library_toggle.setEnabled(False)
            self._enhance_auto_toggle.setEnabled(False)
        except Exception as e:
            log.warning(f"GPU detection error: {e}")
            self._enhance_gpu_status.setText(f"⚠️ Detection error: {e}")
            self._enhance_gpu_status.setStyleSheet(f"color: {Theme.YELLOW};")

        # ── Model Detection (check for Real-ESRGAN weights) ──
        models_dir = Path.home() / ".veoauto" / "models"
        esrgan_path = models_dir / "RealESRGAN_x4plus.pth"
        gfpgan_path = models_dir / "GFPGANv1.4.pth"

        esrgan_ok = esrgan_path.exists()
        gfpgan_ok = gfpgan_path.exists()

        if esrgan_ok and gfpgan_ok:
            total_mb = round((esrgan_path.stat().st_size + gfpgan_path.stat().st_size) / (1024*1024))
            self._enhance_model_status.setText(f"✅ All models installed ({total_mb}MB)")
            self._enhance_model_status.setStyleSheet(f"color: {Theme.GREEN};")
            self._enhance_download_btn.setVisible(False)
        else:
            missing = []
            missing_mb = 0
            if not esrgan_ok:
                missing.append("RealESRGAN")
                missing_mb += 64
            if not gfpgan_ok:
                missing.append("GFPGAN")
                missing_mb += 348
            self._enhance_model_status.setText(f"⬇️ Missing: {', '.join(missing)} (~{missing_mb}MB)")
            self._enhance_model_status.setStyleSheet(f"color: {Theme.YELLOW};")
            self._enhance_download_btn.setVisible(True)
            self._enhance_download_btn.setText(f"⬇️ Download ({missing_mb}MB)")

        # Slow down polling after first check
        self._enhance_check_timer.setInterval(30000)

        # M5 fix: stop timer if both GPU and models are resolved
        try:
            gpu_text = self._enhance_gpu_status.text()
            model_text = self._enhance_model_status.text()
            if gpu_text.startswith('✅') and model_text.startswith('✅'):
                self._enhance_check_timer.stop()
        except Exception:
            pass

    def _on_download_enhancer_models(self):
        """Download Real-ESRGAN + GFPGAN model weights."""
        import logging, threading, urllib.request
        log = logging.getLogger("enhancer")

        models_dir = Path.home() / ".veoauto" / "models"
        models_dir.mkdir(parents=True, exist_ok=True)

        MODELS = [
            ("RealESRGAN_x4plus.pth",
             "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.1.0/RealESRGAN_x4plus.pth"),
            ("GFPGANv1.4.pth",
             "https://github.com/TencentARC/GFPGAN/releases/download/v1.3.0/GFPGANv1.4.pth"),
        ]

        # Filter already downloaded
        to_download = [(name, url) for name, url in MODELS if not (models_dir / name).exists()]
        if not to_download:
            self._enhance_model_status.setText("✅ All models already installed")
            self._enhance_model_status.setStyleSheet(f"color: {Theme.GREEN};")
            return

        self._enhance_download_btn.setEnabled(False)
        self._enhance_download_btn.setText("⏳ Downloading...")
        if self._enhance_progress:
            self._enhance_progress.setVisible(True)
            self._enhance_progress.setValue(0)

        def _download():
            total = len(to_download)
            for idx, (name, url) in enumerate(to_download):
                dest = models_dir / name
                log.info(f"Downloading {name} from {url}")
                QTimer.singleShot(0, lambda n=name: self._enhance_model_status.setText(f"⬇️ Downloading {n}..."))
                try:
                    urllib.request.urlretrieve(url, str(dest))
                    pct = int((idx + 1) / total * 100)
                    if self._enhance_progress:
                        QTimer.singleShot(0, lambda p=pct: self._enhance_progress.setValue(p))
                    log.info(f"Downloaded {name} ({dest.stat().st_size // (1024*1024)}MB)")
                except Exception as e:
                    log.error(f"Failed to download {name}: {e}")
                    QTimer.singleShot(0, lambda: self._on_download_complete(False))
                    return
            QTimer.singleShot(0, lambda: self._on_download_complete(True))

        threading.Thread(target=_download, daemon=True, name="model-download").start()

    def _on_download_complete(self, success: bool):
        """Handle model download completion."""
        if self._enhance_progress:
            self._enhance_progress.setVisible(False)
        self._enhance_download_btn.setEnabled(True)

        if success:
            self._enhance_model_status.setText("✅ All models installed")
            self._enhance_model_status.setStyleSheet(f"color: {Theme.GREEN};")
            self._enhance_download_btn.setVisible(False)
        else:
            self._enhance_model_status.setText("❌ Download failed — retry?")
            self._enhance_model_status.setStyleSheet(f"color: {Theme.RED};")
            self._enhance_download_btn.setText("🔄 Retry Download")

    def _on_install_pytorch(self):
        """Install PyTorch with CUDA via pip — auto-detect Python version for correct index."""
        import logging, sys
        log = logging.getLogger("enhancer")

        # Pick CUDA index based on Python version
        py_ver = sys.version_info
        if py_ver >= (3, 13):
            cuda_index = "https://download.pytorch.org/whl/cu124"
            cuda_label = "CUDA 12.4"
        else:
            cuda_index = "https://download.pytorch.org/whl/cu121"
            cuda_label = "CUDA 12.1"

        pip_cmd = f"pip install torch torchvision torchaudio --index-url {cuda_index}"

        if show_confirm(self, "Install PyTorch (CUDA)",
                f"Python {py_ver.major}.{py_ver.minor} detected → using {cuda_label}\n\n"
                f"This will install PyTorch with CUDA support (~2.5GB).\n\n"
                f"Command:\n{pip_cmd}\n\n"
                f"Continue?"):
            self._enhance_install_btn.setEnabled(False)
            self._enhance_install_btn.setText("⏳ Installing PyTorch...")
            log.info(f"Starting PyTorch installation (Python {py_ver.major}.{py_ver.minor}, {cuda_label})...")

            import subprocess, threading
            def _install():
                try:
                    cmd = [sys.executable, '-m', 'pip', 'install',
                           'torch', 'torchvision', 'torchaudio',
                           '--index-url', cuda_index]
                    log.info(f"Running: {' '.join(cmd)}")
                    result = subprocess.run(
                        cmd, capture_output=True, text=True, timeout=600,
                    )
                    if result.stdout:
                        log.info(f"pip stdout:\n{result.stdout[-2000:]}")
                    if result.stderr:
                        log.warning(f"pip stderr:\n{result.stderr[-2000:]}")
                    success = result.returncode == 0
                    log.info(f"PyTorch install {'succeeded' if success else 'failed'} (rc={result.returncode})")
                except Exception as e:
                    log.error(f"PyTorch install exception: {e}")
                    success = False
                QTimer.singleShot(0, lambda: self._on_pytorch_install_complete(success))

            threading.Thread(target=_install, daemon=True, name="pytorch-install").start()

    def _on_pytorch_install_complete(self, success: bool):
        """Handle PyTorch install completion."""
        self._enhance_install_btn.setEnabled(True)
        if success:
            self._enhance_install_btn.setVisible(False)
            self._enhance_gpu_status.setText("🔄 Restart app to detect GPU")
            self._enhance_gpu_status.setStyleSheet(f"color: {Theme.YELLOW};")
            show_info(
                self, "PyTorch Installed",
                "PyTorch installed successfully!\n\n"
                "Please restart the app to enable GPU detection."
            )
        else:
            import sys as _sys
            _idx = "cu124" if _sys.version_info >= (3, 13) else "cu121"
            self._enhance_install_btn.setText("❌ Install Failed — Retry")
            show_warning(
                self, "Install Failed",
                f"PyTorch installation failed.\n\n"
                f"Try manually:\npip install torch torchvision torchaudio "
                f"--index-url https://download.pytorch.org/whl/{_idx}"
            )

    def _save_enhancer_settings(self, *args):
        """Persist enhancer toggle states to AppSettings."""
        if getattr(self, '_initializing', False):
            return
        try:
            from config.settings import get_settings as _gs
            import logging
            settings = _gs()
            settings.enhance_context_menu = self._enhance_context_toggle.isToggled()
            settings.enhance_library = self._enhance_library_toggle.isToggled()
            settings.enhance_auto_continuation = self._enhance_auto_toggle.isToggled()
            settings.save()
        except Exception as e:
            logging.getLogger('settings').error(f'Failed to save enhancer settings: {e}')
