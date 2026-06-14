# 런북: 공개 리포 정기 보안 점검

공개 리포로 배포하기 전 또는 월 1회, vault 문서와 git 히스토리에
토큰, API 키, 계좌번호, Discord webhook URL 실값이 들어가지 않았는지 확인한다.

## 점검 범위

- `vault/` 전체
- `.env.example`
- `git log -p --all` 전체 히스토리
- `data/`, `.env` 같은 로컬 비밀/상태 디렉토리의 git 추적 여부

## 빠른 점검

```bash
cd agent-hub
git status --short --ignored
git ls-files data .env .env.example vault
```

정상 기준:

- `data/`와 `.env`는 `!!` ignored 상태다.
- `git ls-files data .env` 결과가 비어 있다.
- `.env.example`과 `vault/`만 공개 문서로 추적된다.

## 현재 파일 스캔

```bash
cd agent-hub
rg -n --hidden -S \
  '(token|api[_-]?key|secret|password|passwd|webhook|discord|계좌|account|AKIA|ghp_|github_pat_|sk-|xox[baprs]-|discord\.com/api/webhooks)' \
  vault .env.example
```

이 명령은 후보를 넓게 잡기 때문에 `Discord`라는 단어, 빈 환경변수,
placeholder 설명은 오탐일 수 있다. 실값처럼 보이는 값은 절대 보고문에 그대로
붙여넣지 말고 앞뒤 4자 정도만 남겨 redaction한다.

## 히스토리 스캔

```bash
cd agent-hub
git log -p --all --no-ext-diff --no-color > /tmp/agent-hub-git-log.patch
rg -n -S \
  '(discord\.com/api/webhooks/[0-9]+/|AKIA[0-9A-Z]{16}|ghp_|github_pat_|sk-|xox[baprs]-|BEGIN .*PRIVATE KEY|계좌|account|bank)' \
  /tmp/agent-hub-git-log.patch
rm /tmp/agent-hub-git-log.patch
```

정상 기준:

- Discord webhook URL 실값이 없다.
- bot token, API key, private key, 계좌번호 실값이 없다.
- placeholder와 문서 설명만 나온다.

## 발견 시 대응

실값이 발견되면 즉시 `REQUEST_CHANGES`로 판정하고, 실행 전에 소유자 승인을 받는다.

1. 노출된 서비스별 회전 목록 작성
   - Discord bot token: Developer Portal에서 Reset Token
   - Discord webhook URL: 기존 webhook 삭제 후 새 webhook 생성
   - 외부 API key: 각 서비스 콘솔에서 revoke 후 재발급
   - 계좌번호/개인정보: 공개 필요성 재검토 후 문서에서 제거
2. 현재 작업 트리 백업 또는 별도 브랜치 생성
3. `git filter-repo` 설치 확인

```bash
python -m pip install git-filter-repo
```

4. 파일 전체 제거가 가능하면 경로 기준으로 제거

```bash
git filter-repo --path <leaked-file> --invert-paths
```

5. 특정 문자열만 제거해야 하면 replacement 파일 사용

```bash
printf '<leaked-value>==>REMOVED_SECRET\n' > /tmp/replacements.txt
git filter-repo --replace-text /tmp/replacements.txt
rm /tmp/replacements.txt
```

6. 히스토리 재스캔 후 원격을 강제 갱신

```bash
git log -p --all --no-ext-diff --no-color | rg -n '<redacted-search-pattern>'
git push --force-with-lease --all
git push --force-with-lease --tags
```

강제 갱신 후에는 모든 협업자에게 fresh clone 또는 rebase 절차를 공지한다.
이미 공개된 secret은 히스토리 제거와 무관하게 반드시 회전한다.

## 기록 양식

```text
날짜:
대상 커밋:
검사 범위:
결과: APPROVE / REQUEST_CHANGES
발견 사항:
회전 필요:
히스토리 제거 필요:
검증 명령:
Herald 보고:
```
