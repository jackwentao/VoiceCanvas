"""分镜顺序和名称与每个镜头的画面历史解耦，写入由仓储原子提交。"""

from datetime import UTC, datetime
from typing import Protocol
from uuid import uuid4

from voicecanvas.application.shot_service import ShotConflict, ShotNotFound
from voicecanvas.domain.shot import ShotDocument, ShotRevision
from voicecanvas.domain.storyboard import Storyboard, StoryboardShot, StoryboardState


class StoryboardRepository(Protocol):
    def create(self, board: Storyboard, shots: list[ShotDocument]) -> None: ...
    def load(self, board_id: str) -> Storyboard | None: ...
    def list_recent(self) -> list[Storyboard]: ...
    def load_shots(self, ids: list[str]) -> dict[str, ShotDocument]: ...
    def save(
        self,
        board: Storyboard,
        expected_version: int,
        shots: list[ShotDocument],
        expected_shots: dict[str, int] | None = None,
    ) -> None: ...


class StoryboardService:
    def __init__(self, repository: StoryboardRepository):
        self.repository = repository

    @staticmethod
    def _title(title: str) -> str:
        title = title.strip()
        if not title or len(title) > 100:
            raise ValueError("名称需要 1–100 字")
        return title

    @staticmethod
    def _blank(title: str) -> ShotDocument:
        return ShotDocument(id=f"shot_{uuid4().hex[:16]}", title=title)

    def create(self, title: str) -> Storyboard:
        shot = self._blank("镜头 1")
        state = StoryboardState(
            title=self._title(title),
            shots=[StoryboardShot(id=shot.id, title=shot.title)],
            activeId=shot.id,
        )
        board = Storyboard(id=f"board_{uuid4().hex[:16]}", states=[state], activeId=shot.id)
        self.repository.create(board, [shot])
        return board

    def get(self, board_id: str) -> Storyboard:
        board = self.repository.load(board_id)
        if board is None:
            raise ShotNotFound("分镜项目不存在")
        return board

    def current(self, board_id: str, version: int) -> Storyboard:
        board = self.get(board_id)
        if board.version != version:
            raise ShotConflict("分镜已在其他页面修改，已同步最新状态，请重新操作")
        return board

    def describe(
        self,
        board_id: str,
        version: int,
        *,
        context: str | None = None,
        entries: list[dict] | None = None,
        target_id: str | None = None,
    ) -> Storyboard:
        """Agent 的结构化工具；镜头数量、内容和调用次序由 Agent 决定。"""
        board = self.current(board_id, version)
        state = board.state.model_copy(deep=True)
        created = []
        expected_shots = {}
        if context is not None:
            if len(context) > 2000:
                raise ValueError("共用设定最多 2000 字")
            state.context = context
        if entries:
            if not 1 <= len(entries) <= 12:
                raise ValueError("每次创建 1–12 个镜头")
            documents = self.repository.load_shots([s.id for s in state.shots])
            empty = (
                not target_id
                and len(state.shots) == 1
                and not documents[state.shots[0].id].revisions
                and not state.shots[0].description
            )
            if not target_id and len(state.shots) + len(entries) - int(empty) > 40:
                raise ValueError("项目最多 40 个镜头")
            for index, entry in enumerate(entries):
                if target_id:
                    if len(entries) != 1 or target_id not in documents:
                        raise ValueError("请选择当前项目中的一个镜头")
                    shot_id = target_id
                elif empty and index == 0:
                    shot_id = state.shots[0].id
                    expected_shots[shot_id] = documents[shot_id].version
                else:
                    shot = self._blank(self._title(entry.get("title", "")))
                    created.append(shot)
                    shot_id = shot.id
                item = StoryboardShot.model_validate({**entry, "id": shot_id})
                old = next((s for s in state.shots if s.id == shot_id), None)
                if old:
                    state.shots[state.shots.index(old)] = item
                else:
                    state.shots.append(item)
            state.active_id = state.shots[0].id if empty else board.active_id
        states = [*board.states[: board.cursor + 1], state][-100:]
        changed = Storyboard(
            id=board.id,
            version=version + 1,
            states=states,
            cursor=len(states) - 1,
            activeId=state.active_id,
        )
        self.repository.save(changed, version, created, expected_shots)
        return changed

    def change(
        self,
        board_id: str,
        version: int,
        action: str,
        target_id: str | None = None,
        title: str | None = None,
        position: int | None = None,
        count: int = 1,
        confirmed: bool = False,
    ) -> Storyboard:
        board = self.current(board_id, version)
        state = board.state.model_copy(deep=True)
        new_shots: list[ShotDocument] = []
        target = next(
            (shot for shot in state.shots if shot.id == (target_id or board.active_id)), None
        )
        if target is None:
            raise ValueError("目标镜头不属于当前分镜")
        if action == "switch":
            if target.id == board.active_id:
                return board
            board = board.model_copy(update={"active_id": target.id, "version": version + 1})
            self.repository.save(board, version, [])
            return board
        if action in {"undo", "redo"}:
            cursor = board.cursor + (-1 if action == "undo" else 1)
            if not 0 <= cursor < len(board.states):
                raise ValueError("没有可以撤销或重做的分镜操作")
            restored = board.states[cursor]
            board = board.model_copy(
                update={"cursor": cursor, "active_id": restored.active_id, "version": version + 1}
            )
            self.repository.save(board, version, [])
            return board
        if action == "add":
            if not 1 <= count <= 12 or len(state.shots) + count > 40:
                raise ValueError("每次可新建 1–12 个镜头，每个项目最多 40 个")
            for _ in range(count):
                name = (
                    self._title(title) if title and count == 1 else f"镜头 {len(state.shots) + 1}"
                )
                shot = self._blank(name)
                new_shots.append(shot)
                state.shots.append(StoryboardShot(id=shot.id, title=name))
            state.active_id = new_shots[0].id
        elif action == "rename":
            target.title = self._title(title or "")
            state.active_id = board.active_id
        elif action == "rename_project":
            state.title = self._title(title or "")
            state.active_id = board.active_id
        elif action == "move":
            if position is None or not 1 <= position <= len(state.shots):
                raise ValueError("目标位置超出当前分镜范围")
            state.shots.remove(target)
            state.shots.insert(position - 1, target)
            state.active_id = board.active_id
        elif action == "duplicate":
            if len(state.shots) >= 40:
                raise ValueError("每个项目最多 40 个镜头")
            source = self.repository.load_shots([target.id]).get(target.id)
            if source is None:
                raise ShotNotFound("镜头内容不存在")
            name = target.title[:95] + "（副本）"
            shot = self._blank(name)
            if source.svg:
                shot = shot.model_copy(
                    update={
                        "revisions": [
                            ShotRevision(
                                svg=source.svg,
                                instruction=f"复制镜头：{target.title}",
                                createdAt=datetime.now(UTC).isoformat(),
                            )
                        ],
                        "cursor": 0,
                    }
                )
            new_shots.append(shot)
            state.shots.insert(
                state.shots.index(target) + 1,
                target.model_copy(update={"id": shot.id, "title": name}),
            )
            state.active_id = shot.id
        elif action == "delete":
            if not confirmed:
                raise ValueError("请先确认删除目标镜头")
            if len(state.shots) == 1:
                raise ValueError("至少保留一个镜头，可新建镜头后再删除")
            index = state.shots.index(target)
            state.shots.remove(target)
            state.active_id = (
                state.shots[min(index, len(state.shots) - 1)].id
                if board.active_id == target.id
                else board.active_id
            )
        else:
            raise ValueError("不支持的分镜操作")
        if state.shots == board.state.shots and state.title == board.state.title:
            return board
        states = [*board.states[: board.cursor + 1], state][-100:]
        changed = Storyboard(
            id=board.id,
            version=version + 1,
            states=states,
            cursor=len(states) - 1,
            activeId=state.active_id,
        )
        self.repository.save(changed, version, new_shots)
        return changed
