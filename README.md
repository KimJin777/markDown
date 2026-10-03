# mdEditor

Windows용 마크다운 편집기. 세 칸 [파일 목록 | 원본 | 뷰어]로 쓰고 바로 보고, 여러 파일을 한 번에 인쇄·PDF로 저장한다.

## 설치 (uv)

1. uv가 없으면 PowerShell에서 한 번 설치
   ```powershell
   powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
   ```
2. mdEditor 설치 (파이썬은 uv가 알아서 받는다)
   ```powershell
   uv tool install git+https://github.com/KimJin777/markDown
   ```
   특정 버전: 주소 끝에 `@v0.3.0`
3. 실행: 명령창에서 `mdEditor` (파일을 붙이면 그 파일을 연다: `mdEditor 문서.md`)
   **처음 실행할 때 바탕화면에 `mdEditor` 바로가기가 생긴다.** 지웠으면 메뉴 파일 → 바탕화면에 바로가기 만들기.
4. 업데이트 `uv tool upgrade markdown-editor` / 삭제 `uv tool uninstall markdown-editor`

## 주요 기능

- 여러 파일 올리기(대화상자·끌어다 놓기·폴더), `.txt`는 저장하면 같은 이름의 `.md`가 된다
- 실시간 뷰어(표·코드 블록·체크박스), 뷰어 왼쪽 목차, 원본·뷰어 동시 스크롤(동시보기), 소스 숨기기
- 서식 버튼: 글자 크기·굵게·기울임·밑줄·취소선 (원본이나 뷰어에서 글자를 선택하고 누름)
- 체크한 파일 한꺼번에 인쇄, PDF로 저장(여러 개면 파일마다 `이름.pdf`)
- 맨 아래 상태 표시줄: 파일 경로, 줄/칸, 인코딩·줄바꿈

## 개발

```powershell
uv sync            # 설치
run.bat            # 실행
uv run pytest      # 테스트
build.bat          # 실행 파일 → dist\mdEditor\mdEditor.exe (폴더째 배포)
```

변경 이력: [CHANGELOG.md](CHANGELOG.md)
