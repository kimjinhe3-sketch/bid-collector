# Streamlit Community Cloud 배포 가이드

Streamlit 커뮤니티 클라우드는 GitHub 리포만 있으면 **무료**로 앱을 호스팅해 줍니다. URL이 발급되어 PC/태블릿/모바일 어디서든 브라우저로 접속할 수 있습니다.

## 사전 준비
- [ ] GitHub 계정 (https://github.com/join, 무료)
- [ ] Git 설치 (https://git-scm.com/download/win) — "Git Bash" 포함 설치 권장
- [ ] 공공데이터포털 G2B 서비스키

## 1단계 — GitHub 리포 생성 (5분)

1. https://github.com/new 접속
2. Repository name: `bid-collector` (아무거나 OK)
3. **Private** 선택 (입찰 데이터 노출 방지)
4. "Create repository" 클릭

## 2단계 — 로컬 프로젝트를 GitHub에 업로드

Git Bash 또는 PowerShell에서:

```bash
cd "C:/Users/user/BID SEARCHING TOOL/bid_collector"
git init
git add .
git commit -m "initial commit"
git branch -M main
git remote add origin https://github.com/<본인아이디>/bid-collector.git
git push -u origin main
```

> `.env` 파일은 `.gitignore`에 포함되어 있어 자동으로 제외됩니다. **API 키가 리포에 올라가지 않았는지** GitHub 웹에서 확인하세요.

## 3단계 — Streamlit Cloud에 앱 배포

1. https://streamlit.io/cloud 접속 → "Sign up with GitHub"
2. 로그인 후 **"New app"** 클릭
3. 양식 작성:
   - Repository: `<본인아이디>/bid-collector`
   - Branch: `main`
   - Main file path: `dashboard/app.py`
   - Python version: `3.11` (자동 감지됨 — `runtime.txt` 덕분)
4. **"Advanced settings"** → **Secrets** 탭 열기
5. 아래 내용 붙여넣고 값만 본인 것으로 교체:

```toml
G2B_SERVICE_KEY = "여기에_본인_서비스키"
KAPT_SERVICE_KEY = ""
SMTP_USER = ""
SMTP_PASS = ""
SLACK_WEBHOOK_URL = ""
```

6. **"Deploy!"** 클릭 → 3~5분 후 URL 발급 (`https://your-app.streamlit.app`)

## 4단계 — 첫 수집

1. 발급된 URL 접속
2. 좌측 사이드바에서 **"🚀 지금 수집"** 클릭
3. 2~3분 대기 → 대시보드에 공고 목록 표시

## 모바일 접속

발급된 URL을 폰 브라우저에서 열면 자동으로 모바일 레이아웃 적용.
- Chrome: 메뉴 → "홈 화면에 추가" → 앱 아이콘처럼 실행
- Safari: 공유 → "홈 화면에 추가"

## 데이터 지속성 주의 ⚠️

Streamlit Community Cloud는 **임시 파일 시스템**이라 앱이 재시작되면 `data/bids.sqlite`가 사라집니다.

- **현재 동작**: 앱이 깨어있는 동안에는 데이터 유지 (최장 1~2일)
- **권장 사용법**: 대시보드 접속해서 "지금 수집" 클릭 → 결과 확인
- **장기 보관이 필요하면**: 외부 DB(Supabase, Turso 등) 연동 필요 — 추가 작업

## 스케줄러 (매일 자동 수집)

Streamlit Cloud는 상시 스케줄러를 돌리기 부적합합니다. 대안:

- **GitHub Actions**: `.github/workflows/` 에 매일 아침 워크플로우 추가 (추후 지원)
- **외부 cron 서비스**: cron-job.org 등에서 매일 앱 URL 호출
- **수동**: 사이드바에서 "지금 수집" 버튼 클릭

## 코드 업데이트

로컬에서 수정 후:

```bash
git add .
git commit -m "update dashboard"
git push
```

→ Streamlit Cloud가 자동으로 재배포 (1~2분 소요)

## 문제 해결

| 증상 | 원인 / 해결 |
|---|---|
| 배포 실패 "No module named X" | `requirements.txt`에 누락된 패키지 추가 후 push |
| 수집 중 SSL 오류 | 로컬에선 `truststore`가 해결, Cloud(Linux)에선 자동으로 정상 동작 |
| "G2B_SERVICE_KEY not set" | Secrets 탭에 키 입력 후 앱 Reboot |
| 앱 느림 | Streamlit Cloud 무료 티어는 1GB RAM — 수집은 오래 걸릴 수 있음 |

---

## 로컬 개발 (지금처럼)

배포와 무관하게 로컬에서 계속 돌릴 수 있습니다.
- `.env` 파일로 시크릿 관리
- `시작.bat` 더블클릭으로 실행
- 로컬에서 수정 후 Git push → 배포도 자동 갱신
