# ADR-0004: 업로드 운영 모델 — API는 초안 적재, 공개는 사람이 결정

- 날짜: 2026-06-12
- 상태: 채택

## 배경

쇼츠 파이프라인 6단계로 YouTube 업로드가 필요하다. 하지만 YouTube Data API 업로드는
외부 게시 행위이며, 잘못 공개되면 회수 비용이 크다. 또한 YouTube 공식 문서 기준으로
2020-07-28 이후 생성된 미인증 API 프로젝트에서 `videos.insert`로 업로드한 영상은
private viewing mode로 제한될 수 있다. 솔로 운영자가 API compliance audit을 통과해
완전 자동 공개까지 맡기는 모델은 리스크가 크다.

2026-06-12 재확인 기준:

- `videos.insert`는 Video Uploads quota bucket에서 기본 100 calls/day로 관리된다.
- `videos.insert` 요청 본문은 `status.privacyStatus`와
  `status.selfDeclaredMadeForKids`를 설정할 수 있다.
- YouTube Data API는 사용자 데이터 접근에 OAuth 2.0을 사용하며, 서비스 계정은
  YouTube 계정 연결이 없어 업로드 경로에 적합하지 않다.

## 결정

1. API 업로드는 `private` 또는 `unlisted`만 허용한다.
2. `privacy='public'`은 코드에서 `ValueError`로 즉시 차단한다.
3. 실제 공개 전환은 사람이 YouTube Studio에서 영상, 제목, 설명, BGM 출처,
   아동용 여부를 확인한 뒤 직접 수행한다.
4. CLI 업로드 경로는 `bus add --approve`에 해당하는 승인 task 생성, `bus wait`,
   승인 확인 후 `videos.insert` 실행 순서로만 동작한다.
5. 실제 insert 실행 함수는 승인된 `youtube_upload` task id를 요구하고,
   task 본문에 `episode_dir`와 `privacy`가 일치해야 실행된다.
6. `needs_approval` 작업의 `approved/rejected` 상태 전환은 `hermes.bus set-status`
   CLI에서 차단한다. Discord 승인 버튼이 상태 전환 경로다.
7. OAuth client secret과 refresh token은 `data/client_secret.json`,
   `data/youtube_token.json`에 저장한다. `data/`는 git 추적 대상이 아니다.
8. `publish_history` 테이블에 `episode_dir`를 primary key로 기록해 동일 에피소드의
   중복 업로드를 차단한다.

## 근거

- 외부 게시는 HITL 승인 불변식을 따라야 한다.
- 미인증 프로젝트의 private 제한 때문에 API로 `public`을 요청하는 것은 운영자에게
  잘못된 기대를 준다.
- `unlisted` 적재 후 사람이 Studio에서 최종 공개하는 방식은 자동화 이득을 유지하면서
  제목/설명/저작권/아동용 여부를 마지막에 점검할 수 있다.
- 업로드 scope를 `https://www.googleapis.com/auth/youtube.upload`로 제한하면 토큰 권한이
  필요한 범위를 넘지 않는다.

## 대안과 기각 사유

- API로 `public` 직접 업로드: 미인증 프로젝트 private 잠금과 오발행 리스크 때문에 기각.
- YouTube compliance audit 후 완전 자동 공개: 솔로 운영 비용과 심사 부담이 커서 현 단계
  목표에 맞지 않아 기각.
- 수동 업로드만 사용: 렌더링 산출물을 Studio에 직접 올릴 수는 있지만 반복 작업이 커져
  6단계 자동화 목표를 달성하지 못해 기각.
- 서비스 계정 사용: YouTube Data API 업로드에는 사용자 YouTube 계정 OAuth가 필요하므로
  기각.

## 영향

- 쇼츠 생산자는 `python -m pipelines.shorts.upload <episode_dir>`를 실행하면 Discord
  승인 후 `unlisted` 또는 `private` 영상이 생성된다.
- 공개 전환은 자동화 밖의 사람 책임으로 남는다.
- `publish_history`에 기록된 에피소드는 재업로드가 차단된다.
- `client_secret.json`과 `youtube_token.json`이 `data/` 밖에 생기면 보안 점검 실패로 본다.
