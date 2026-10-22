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
4. 업데이트: 프로그램에서 도움말 → 업데이트 확인(새 버전이 있으면 [지금 업데이트]로 닫고 받아 다시 켬), 또는 `uv tool upgrade markdown-editor` / 삭제 `uv tool uninstall markdown-editor`

## 주요 기능

- 여러 파일 올리기(대화상자·끌어다 놓기·폴더), 폴더는 하위 폴더까지 트리로 보이고 폴더를 체크하면 안의 파일이 모두 체크된다(오른쪽 클릭으로 하위 폴더까지 모두 펼치기·접기). `.txt`는 저장하면 같은 이름의 `.md`가 된다
- 실시간 뷰어(표·코드 블록·체크박스), Mermaid 다이어그램(흐름도·시퀀스·클래스·상태·ER·간트·차트 등), 뷰어 왼쪽 목차, 원본·뷰어 동시 스크롤(동시보기), 소스 숨기기
- 서식 버튼: 글자 크기·굵게·기울임·밑줄·취소선 (원본이나 뷰어에서 글자를 선택하고 누름)
- [빈칸] 밑줄 빈칸·빈칸·괄호 빈칸 넣기(글자를 고르고 누르면 그 자리가 빈칸), [특수기호] 문자표(Ctrl+F10)
- [A4 쪽 선] 뷰어를 A4 인쇄 폭으로 맞추고 쪽이 끝나는 곳에 점선(인쇄 미리 가늠)
- 찾기(Ctrl+F)·바꾸기(Ctrl+H)·다음/이전 찾기(F3/Shift+F3), 모두 바꾸기는 Ctrl+Z 한 번으로 되돌림
- 체크한 파일 한꺼번에 인쇄, PDF로 저장(여러 개면 파일마다 `이름.pdf`)
- 맨 아래 상태 표시줄: 파일 경로, 줄/칸, 인코딩·줄바꿈
- JSON·YAML·CSV(TSV)는 표로(열마다 글자색), PDF·그림(.png .jpg 등)·HWP(.hwp .hwpx)는 보기 전용으로 연다
- PDF·HWP를 마크다운으로 바꾸기 [MD로 바꾸기](Ctrl+Shift+M) — 글자·표·그림(옆 '이름_images' 폴더), 특허로 같은 전자 양식(XFA) PDF는 입력된 값을 뽑음
- 다른 프로그램이 파일을 고치면 목록에 ↻ 표시 → [새로 불러오기](F5). 새로 불러오면 바뀐 부분이 파란색으로 보이고, 다 봤으면 [검토완료]로 보통 색으로 돌린다. 보기 메뉴에서 자동으로 다시 읽기도 켤 수 있다
- 파일 목록 정렬(이름·종류·폴더·고친 시각)
- 그림 슬라이드(문서의 그림만 한 장씩 크게, ← → 넘기기), 전체 화면 보기(F11)
- .md 파일 연결: 파일 → '.md 파일을 mdEditor로 열기 등록...' 후 나오는 창에서 mdEditor → '항상'. 이미 켜져 있으면 더블클릭한 파일이 그 창에 올라간다
- 도움말 → 새 기능·변경 이력: 프로그램 안에서 버전별로 바뀐 내용 보기(새 버전으로 처음 켜면 자동으로 한 번)

## 개발

```powershell
uv sync            # 설치
run.bat            # 실행
uv run pytest      # 테스트
build.bat          # 실행 파일 → dist\mdEditor\mdEditor.exe (폴더째 배포)
```

변경 이력: [CHANGELOG.md](CHANGELOG.md)

## 라이선스

[GNU AGPL v3.0 이상](LICENSE). PDF→마크다운 변환에 쓰는 PyMuPDF·pymupdf4llm(AGPL)을 따른다.
흐름도 렌더링에는 Mermaid Tiny(MIT, `src/mdeditor/vendor/MERMAID-LICENSE.txt`)를 사용한다.
mdEditor를 고쳐서 배포하거나 서비스하면 고친 소스도 같은 라이선스로 공개해야 한다.
