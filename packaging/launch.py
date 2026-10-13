"""실행 파일(PyInstaller) 진입점."""

import multiprocessing

from mdeditor.app import main

if __name__ == "__main__":
    multiprocessing.freeze_support()  # PDF→MD(pymupdf 레이아웃 분석)가 작업 프로세스를 띄울 때 필요
    main()
