"""Smoke test UI: filtro libreria disaccoppiato e layout top bar / splitter."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication

from db import db_core
from services.app_mode_service import AppModeService
from services.library_service import LibraryService
from services.queue_service import QueueService
from ui.main_window import MainWindow
from ui.theme_service import ThemeService

_app = QApplication.instance() or QApplication([])


def _make_window() -> MainWindow:
    """Costruisce MainWindow dry-run con libreria reale."""
    db_core.migrate()
    conn = db_core.get_conn()
    library = LibraryService(conn)
    queue = QueueService(conn, 1)
    theme_service = ThemeService()
    theme_service.apply_globally()
    window = MainWindow(
        AppModeService(),
        None,
        None,
        queue,
        None,
        library_service=library,
        theme_service=theme_service,
        dry_run=True,
    )
    window.resize(1200, 800)
    window.show()
    _app.processEvents()
    return window


def test_library_tab_not_filtered_by_search_query() -> None:
    """Passare a Libreria dopo una ricerca non deve applicare il filtro Ricerca."""
    window = _make_window()
    total = len(LibraryService(db_core.get_conn()).list_tracks())
    assert total > 0, "serve almeno un brano in libreria per il test"

    window._search_input.setText("take it easy eagles karaoke query lunga")
    window._tabs.setCurrentWidget(window._library_widget)
    window._on_tab_changed(window._tabs.currentIndex())
    _app.processEvents()

    assert window._library_widget._list.count() == total
    assert window._library_widget.active_filter() == ""
    window.close()


def test_library_internal_filter() -> None:
    """Il filtro dedicato in Libreria restringe la lista senza toccare Ricerca."""
    window = _make_window()
    window._tabs.setCurrentWidget(window._library_widget)
    window._on_tab_changed(window._tabs.currentIndex())
    _app.processEvents()

    window._library_widget.filter("zzzznonexistent999")
    _app.processEvents()
    assert window._library_widget._list.count() == 0
    assert window._library_widget.active_filter() == "zzzznonexistent999"

    window._library_widget.clear_filter()
    _app.processEvents()
    assert window._library_widget._list.count() > 0
    window.close()


def test_top_bar_and_splitter_layout() -> None:
    """La top bar resta compatta e l'anteprima riceve spazio verticale adeguato."""
    window = _make_window()
    window._apply_initial_splitter_sizes()
    _app.processEvents()

    main_y = window._main_splitter.geometry().y()
    filler_h = window._filler_source.height()
    video_h = window._video_output.height()
    left_sizes = window._left_splitter.sizes()

    assert main_y < 120, f"top bar troppo alta: main_splitter y={main_y}"
    assert filler_h <= 72, f"FillerSourceWidget troppo alto: {filler_h}px"
    assert video_h >= 250, f"anteprima troppo piccola: {video_h}px"
    assert left_sizes[0] > left_sizes[1] * 0.5, f"splitter sbilanciato: {left_sizes}"
    assert window._player_widget._set_start_btn.text() == "Inizia da qui"
    assert window._player_widget._set_start_btn.isVisible()
    window.close()


def test_filler_long_source_label_stays_on_second_row() -> None:
    """Un nome sottofondo lungo non deve espandere la riga dei controlli."""
    window = _make_window()
    window._filler_source.set_source_label(
        "Brano con titolo molto lungo che prima spingeva fuori shuffle e volume — artista.mp4"
    )
    _app.processEvents()
    label_y = window._filler_source._source_label.y()
    shuffle_y = window._filler_source._shuffle_check.y()
    assert label_y > shuffle_y, "l'etichetta sorgente deve stare sotto i controlli"
    window.close()


def test_f11_maximizes_preview() -> None:
    """F11 collassa controlli e coda lasciando solo l'anteprima."""
    window = _make_window()
    window._apply_initial_splitter_sizes()
    _app.processEvents()
    saved_controls = window._left_splitter.sizes()[1]
    assert saved_controls > 0

    window._toggle_preview()
    _app.processEvents()
    assert window._preview_maximized
    assert window._left_splitter.sizes()[1] == 0
    assert window._main_splitter.sizes()[1] == 0

    window._toggle_preview()
    _app.processEvents()
    assert not window._preview_maximized
    assert window._left_splitter.sizes()[1] == saved_controls
    window.close()


def test_vlc_resize_callback_invoked() -> None:
    """Il widget video propaga il resize al callback VLC (debounced)."""
    window = _make_window()
    received: list[object] = []
    window.set_vlc_output_rebind(lambda widget: received.append(widget))
    window._left_splitter.setSizes([700, 180])
    window.resize(1300, 850)
    _app.processEvents()
    QTimer.singleShot(250, _app.quit)
    _app.exec()
    assert received, "callback VLC non invocato al ridimensionamento anteprima"
    window.close()


def test_theme_switch_light_and_dark() -> None:
    """Le pill Chiaro/Scuro applicano i QSS globali e aggiornano lo stato UI."""
    window = _make_window()
    theme_service = window._theme_service
    assert theme_service is not None

    theme_service.set_theme("dark")
    _app.processEvents()
    assert "#2b4a6e" in _app.styleSheet().lower()
    assert window._theme_dark_btn.objectName() == "themeToggleActive"

    theme_service.set_theme("light")
    _app.processEvents()
    assert "#e8f1fa" in _app.styleSheet().lower()
    assert window._theme_light_btn.objectName() == "themeToggleActive"

    window._on_theme_dark_clicked()
    _app.processEvents()
    assert theme_service.current_theme() == "dark"
    assert "#2b4a6e" in _app.styleSheet().lower()
    window.close()


def _run_all() -> None:
    """Esegue tutti i test e segnala errori."""
    tests = [
        test_library_tab_not_filtered_by_search_query,
        test_library_internal_filter,
        test_top_bar_and_splitter_layout,
        test_f11_maximizes_preview,
        test_vlc_resize_callback_invoked,
        test_theme_switch_light_and_dark,
    ]
    failed = 0
    for test in tests:
        name = test.__name__
        try:
            test()
            print(f"OK  {name}")
        except Exception as exc:
            failed += 1
            print(f"FAIL {name}: {exc}")
    if failed:
        raise SystemExit(f"{failed} test falliti")
    print(f"Tutti i {len(tests)} test superati.")


if __name__ == "__main__":
    _run_all()
    QTimer.singleShot(0, _app.quit)
    _app.exec()
    db_core.close()
