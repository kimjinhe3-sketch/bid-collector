# KT Engineering CRM — Design System 적용 가이드

본 문서는 `design/` 폴더의 KT 그룹 BI/CI/UX 자료를 정독하여 도출한 시스템 적용 규칙이다. **모든 신규 컴포넌트와 화면은 이 가이드를 우선 따른다.** 변경이 필요할 때는 이 문서와 토큰을 함께 갱신한다.

## 1. 브랜드 컬러 (Brand Color)

### 1-1. 프라이머리 컬러
| 토큰 | HEX | RGB | 용도 |
|---|---|---|---|
| **kt-red** | `#FE2E36` | 254 46 54 | **프라이머리 (디지털 화면 표준)** |
| kt-red-bi | `#ED2024` | 237 32 36 | BI 인쇄용 (CMYK 0/100/100/0, Pantone 1795C) |

→ 화면에서는 항상 `#FE2E36` 사용. 인쇄물·서류 출력 PDF 생성 시에만 `#ED2024` 사용.

### 1-2. 매칭 컬러 (보조)
| 토큰 | HEX | 의미 부여 |
|---|---|---|
| kt-purple | `#AA50FF` | 강조·특별 (예: VIP 표시) |
| kt-blue | `#00A5FF` | 정보·링크 |
| kt-teal | `#00BEAC` | 성공·수주 완료 |

### 1-3. 모노톤
| 토큰 | HEX |
|---|---|
| kt-black | `#000000` |
| kt-dark-gray | `#4C4C4E` |
| kt-light-gray | `#A2A4A3` |
| kt-white | `#FFFFFF` |

### 1-4. 시맨틱 매핑 (CRM 도메인)
| 의미 | 컬러 |
|---|---|
| 프라이머리 액션 (등록·확인) | kt-red |
| 위험·실주·삭제 | kt-red (강도 ↑) |
| 정보·링크·필터 | kt-blue |
| 성공·수주·완료 | kt-teal |
| 강조·VIP·승인 | kt-purple |
| 본문·헤더 텍스트 | kt-black / kt-dark-gray |
| 비활성·구분선·placeholder | kt-light-gray |
| 배경·카드 | kt-white / muted (slate-50) |

### 1-5. 파이프라인 스테이지 컬러
| 스테이지 | 컬러 | 의미 |
|---|---|---|
| lead (발굴) | slate | 진입 단계 |
| qualified (검증) | kt-blue | 정보 확인 중 |
| proposal (제안) | kt-purple | 강조 단계 |
| negotiation (협상) | amber | 결정 임박 |
| won (수주) | kt-teal | 성공 |
| lost (실주) | kt-red | 실패 |
| dropped (드랍) | kt-light-gray | 이탈 |

## 2. 타이포그래피 — KT Flow

### 2-1. 서체 정보
- **KT 그룹 전용 서체**: KT Flow (Black / Bold / Medium / Thin 4종)
- 디자인 콘셉트: 곡률(Flow) — 직선과 곡선의 기하학적 조화, 좌상단·우하단 라운드 디테일

### 2-2. 적용 방식
- `app/fonts/KTFlow-*.ttf` 파일을 `next/font/local`로 등록
- CSS 변수: `--font-kt-flow`
- Tailwind `font-sans` 의 첫 번째 fallback으로 지정
- 한글은 KT Flow가 라틴 중심이므로 **Noto Sans KR**과 결합 (한글 가독성 보강)

### 2-3. 타이포그래피 스케일
| 클래스 | 크기 | weight | 용도 |
|---|---|---|---|
| `text-3xl font-black` | 30px / 900 | KT Flow Black | 대시보드 핵심 수치 |
| `text-2xl font-bold` | 24px / 700 | KT Flow Bold | 페이지 타이틀 |
| `text-lg font-bold` | 18px / 700 | KT Flow Bold | 섹션 타이틀 |
| `text-base font-medium` | 16px / 500 | KT Flow Medium | 본문 강조 |
| `text-sm` | 14px / 400 | Noto Sans KR Regular | 본문 |
| `text-xs` | 12px / 400 | Noto Sans KR Regular | 메타 정보 |

> KT Flow는 라틴 중심이므로 한글 본문(text-sm 이하)은 자동으로 Noto Sans KR로 떨어진다. 수치·영문·헤딩은 KT Flow 우선.

## 3. CI 로고 (kt engineering)

### 3-1. 자산
- 라이트 배경용: `public/logos/kt-engineering-light.png` (`kt`=검정, `engineering`=빨강)
- 다크 배경용: `public/logos/kt-engineering-dark.png` (전체 빨강 + 흰 배경 가시성용)

### 3-2. 사용 규칙
- **로그인 카드**: 라이트 로고
- **사이드바**: 다크 로고 (사이드바 배경이 KT BLACK)
- **로고 최소 높이**: 데스크톱 28px, 모바일 24px
- **여백**: 로고 좌우에 최소 12px(모바일) / 16px(데스크톱) padding
- **변형 금지**: 색상 임의 변경, 비율 변경, 회전, 그림자 추가 금지

## 4. UX 컴포넌트 (KT 디자인 시스템 매핑)

`design/kt_UX.md`에 정의된 24개 컴포넌트 → shadcn/ui 매핑:

| KT 컴포넌트 | shadcn/ui | 본 프로젝트 활용 단계 |
|---|---|---|
| Button | button | Phase 1 ✅ |
| Bottom Navigation | (커스텀) | Phase 1 ✅ |
| Bottom Sheet | sheet | Phase 5 (모바일 첨부 업로드) |
| Card | card | Phase 1 ✅ |
| Checkbox | checkbox | Phase 3 (필터) |
| Chip | badge (custom) | Phase 3 (스테이지 표시) |
| Data Visual | recharts | Phase 4 |
| Data Table | (custom + tanstack-table) | Phase 3 (리스트 뷰) |
| Divider | separator | 전반 |
| Dropdown | dropdown-menu | Phase 1 부분 ✅ |
| Indicator | (custom) | Phase 6 (알림 배지) |
| List | (custom) | 전반 |
| Loading | (custom Spinner) | 전반 |
| Notification | toast | Phase 3+ (sonner 권장) |
| Popup | dialog | Phase 5 (변경계약 추가) |
| Radio Button | radio-group | Phase 3 |
| Search | input + search icon | Phase 3 |
| Slider | slider | Phase 3 (수주확률 0~100%) |
| Switch | switch | Phase 7 (Admin 토글) |
| Tab | tabs | Phase 3 (칸반/리스트 전환) |
| Tag | badge | 전반 |
| Text Field | input | Phase 1 ✅ |
| Tooltip | tooltip | 전반 |
| Top Navigation | (커스텀 Header) | Phase 1 ✅ |

### 컴포넌트 작성 원칙
- shadcn/ui 베이스 위에서 KT 토큰(컬러·폰트·반경)을 덮어쓰는 방식
- 새 컴포넌트가 필요하면 KT UX 컴포넌트 표준 시그니처 우선 (variant·size·state)
- 모서리 반경: 기본 `rounded-md`(8px), 카드는 `rounded-lg`(12px), 칩/배지는 `rounded-full`

## 5. 레이아웃 규칙

### 5-1. 사이드바 (데스크톱 lg+)
- 너비: 240px (`w-60`)
- 배경: KT BLACK `#000000`
- 텍스트: KT WHITE / hover시 white/10 overlay
- active 표시: 좌측 4px KT RED 인디케이터 + white/15 배경

### 5-2. 헤더
- 높이: 64px (`h-16`)
- 배경: KT WHITE
- 하단 보더: 1px slate-200
- 우측: 알림 벨 + 사용자 정보 + 로그아웃

### 5-3. Bottom Navigation (모바일 <lg)
- 높이: 64px (`h-16`)
- 4 탭 균등 배분
- active: KT RED 텍스트 + 아이콘 + 상단 2px 인디케이터

### 5-4. 그리드·여백
- 페이지 main padding: 모바일 16px, 데스크톱 32px
- 카드 사이 간격: 16px (`gap-4`)
- 섹션 사이 간격: 24px (`space-y-6`)

## 6. 인터랙션 가이드

- **버튼 hover/active**: 기본 색상의 shade 한 단계 진하게 (예: kt-red → kt-red/90)
- **focus 링**: 2px outline + 2px offset, 컬러는 ring (KT RED 기반)
- **transition**: `transition-colors duration-150` 기본
- **loading**: 버튼 내 스피너 + 텍스트 변경 ("로그인 중..." 식)
- **에러**: kt-red 텍스트 + role="alert"

## 7. 다크 모드 정책

본 시스템은 **Phase 1~7 동안 라이트 모드만 지원**한다. 다크 모드는 Phase 8 이후 별도 토큰셋으로 추가. 단:
- CI 로고는 다크 모드용 자산을 미리 보유 (`kt-engineering-dark.png`)
- 사이드바는 라이트 모드 환경에서도 KT BLACK 배경 사용 (의도된 contrast)

## 8. 변경 시 갱신 대상

색상·폰트·로고 변경이 필요하면 다음을 함께 갱신:
1. `app/globals.css` — CSS 변수
2. `tailwind.config.ts` — 컬러 토큰
3. `app/layout.tsx` — 폰트 등록
4. `components/layout/brand-logo.tsx` — 로고 컴포넌트
5. `types/domain.ts` — `STAGE_COLORS` 등 도메인 컬러 매핑
6. 본 문서 (DESIGN_SYSTEM.md)
