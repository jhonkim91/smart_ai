# 런북: YouTube OAuth 업로드 준비

YouTube Shorts 업로드는 OAuth Desktop app credential로만 수행한다.
`client_secret.json`과 refresh token은 반드시 `data/` 아래에만 둔다.
`data/`는 `.gitignore`에 포함되어 있으므로 공개 리포에 올라가지 않는다.

## Google Cloud 설정

1. Google Cloud Console에 로그인한다.
2. 새 프로젝트를 만든다.
3. API Library에서 `YouTube Data API v3`를 검색해 Enable한다.
4. OAuth consent screen을 설정한다.
   - User type: `External`
   - Publishing status: 테스트 단계 유지
   - Test users: 업로드할 내 Google/YouTube 계정을 추가
   - Scope: `https://www.googleapis.com/auth/youtube.upload`
5. Credentials 메뉴에서 `Create credentials` -> `OAuth client ID`를 선택한다.
6. Application type은 `Desktop app`으로 만든다.
7. JSON 파일을 내려받아 아래 경로에 저장한다.

```bash
cd agent-hub
mkdir -p data
mv ~/Downloads/client_secret_*.json data/client_secret.json
chmod 600 data/client_secret.json
```

## 최초 브라우저 인증

```bash
cd agent-hub
source .venv/bin/activate
python -m pipelines.shorts.auth_youtube
chmod 600 data/youtube_token.json
```

브라우저가 열리면 테스트 사용자로 등록한 계정으로 로그인하고 YouTube 업로드 권한을
승인한다. 성공하면 `data/youtube_token.json`이 생성된다.

## 업로드 실행

업로드는 반드시 Discord HITL 승인을 거친다. API에서 허용하는 privacy는
`unlisted` 또는 `private`뿐이다. `public`은 코드에서 즉시 거부된다.

```bash
cd agent-hub
source .venv/bin/activate
python -m channel.discord_bot
```

다른 터미널에서:

```bash
cd agent-hub
source .venv/bin/activate
python -m pipelines.shorts.upload data/shorts/<episode_dir> --privacy unlisted
```

승인 채널에 카드가 올라오면 사람이 내용을 확인하고 승인한다. 승인 후에만
`videos.insert`가 실행된다.

## Dry-run 검증

실제 업로드 없이 승인 흐름과 요청 바디만 확인할 때 사용한다.

```bash
python -m pipelines.shorts.upload data/shorts/<episode_dir> --privacy unlisted --dry-run
```

주의: dry-run도 승인 카드가 올라오며, 승인 후에만 요청 바디가 출력된다.

## 공개 전환

API는 영상을 `unlisted` 또는 `private` 상태로 적재하는 데만 사용한다.
최종 공개는 사람이 YouTube Studio에서 영상, 제목, 설명, 음악 출처, 아동용 여부를
확인한 뒤 직접 `Public`으로 전환한다.

## 문제 해결

- `client_secret.json 없음`: Google Cloud에서 Desktop app credential을 내려받아
  `data/client_secret.json`으로 저장한다.
- `access_denied`: OAuth consent screen의 Test users에 로그인 계정을 추가한다.
- 같은 에피소드 중복 업로드 차단: `publish_history`에 해당 `episode_dir` 기록이 있다.
  실제 업로드가 이미 끝난 경우 재실행하지 않는다. 프로세스 중단으로 예약만 남은 경우
  SQLite를 열어 `video_id IS NULL`인지 확인한 뒤 운영자가 수동 정리한다.
- 업로드가 private으로 잠김: 2020-07-28 이후 생성된 미인증 API 프로젝트의 정책상
  발생할 수 있다. 공개 전환은 YouTube Studio에서 사람이 수행한다.
