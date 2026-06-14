# 런북: Discord 봇

Discord 봇은 작업 접수, HITL 승인 카드 게시, 승인/거부 버튼 처리를 담당한다.
승인 버튼은 `discord.py` `DynamicItem` 패턴을 사용하므로 봇 재시작 후에도
기존 카드의 `custom_id`에서 작업 ID와 액션을 복원한다.

## 기동

```bash
cd agent-hub
source .venv/bin/activate
python -m channel.discord_bot
```

필수 환경변수는 `.env`에 둔다.

```bash
DISCORD_BOT_TOKEN=...
DISCORD_GUILD_ID=...
DISCORD_APPROVAL_CHANNEL_ID=...
DISCORD_WEBHOOK_URL=...
```

## 승인 카드 재시작 검증

봇이 켜진 터미널은 별도 창으로 유지한다.

```bash
cd agent-hub
source .venv/bin/activate
tid=$(python -m hermes.bus add "probe: restart approval $(date +%s)" --approve)
python -m hermes.bus get "$tid"
```

1. 승인 채널에 작업 카드가 올라왔는지 확인한다.
2. 봇 터미널에서 `Ctrl-C`로 종료한다.
3. 봇을 다시 시작한다.

```bash
python -m channel.discord_bot
```

4. 재시작 전에 올라온 카드에서 `승인` 버튼을 누른다.
5. SQLite 상태가 `approved`로 바뀌었는지 확인한다.

```bash
python -m hermes.bus get "$tid"
```

정상 결과:

- Discord 카드 footer가 `승인됨`으로 바뀐다.
- 승인/거부 버튼이 비활성화된다.
- `python -m hermes.bus get "$tid"` 결과의 `status`가 `approved`다.

## 이미 처리된 카드 검증

카드는 아직 활성화되어 있지만 DB 상태가 먼저 바뀐 상황을 만든다.

```bash
cd agent-hub
source .venv/bin/activate
tid=$(python -m hermes.bus add "probe: stale approval $(date +%s)" --approve)
python -m hermes.bus get "$tid"
```

승인 채널에 카드가 올라온 뒤, 버튼을 누르기 전에 상태를 바꾼다.

```bash
python -m hermes.bus set-status "$tid" approved
python -m hermes.bus get "$tid"
```

그 다음 Discord 카드의 `승인` 또는 `거부` 버튼을 누른다.

정상 결과:

- 클릭한 사용자에게만 `이미 처리된 요청입니다. 현재 상태: ...` 안내가 보인다.
- 카드 버튼이 비활성화된다.
- SQLite 상태는 기존 값에서 다시 바뀌지 않는다.

## 로컬 회귀 검증

외부 Discord 클릭 없이 코드 경로를 확인할 때는 unittest를 실행한다.

```bash
cd agent-hub
source .venv/bin/activate
python -m unittest discover -s tests -v
python -m compileall hermes channel tests
```

검증 범위:

- `custom_id`가 `hermes:approval:(approve|reject):<task_id>` 형식인지 확인
- `DynamicItem.from_custom_id()`가 재시작 후 클릭처럼 작업 ID와 액션을 복원
- `pending` 작업만 조건부 UPDATE로 `approved`/`rejected` 전환
- 이미 처리된 작업 재클릭 시 ephemeral 안내와 카드 비활성화
