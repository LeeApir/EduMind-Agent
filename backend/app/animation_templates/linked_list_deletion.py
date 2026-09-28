"""Fixed Manim scene for safe singly linked list deletion."""

import json
import os

from manim import (  # type: ignore[import-not-found]
    DOWN,
    LEFT,
    RIGHT,
    UP,
    Arrow,
    FadeIn,
    FadeOut,
    RoundedRectangle,
    Scene,
    Text,
    VGroup,
)

from app.animation_templates.deletion_plan import DeletionFrame, plan_deletion

VALUES = [1, 3, 5]
INDEX = 1
PARAMETERS_ENV = "EDUMIND_ANIMATION_PARAMETERS"
ONSCREEN_NOTES = (
    "Find predecessor, target, and successor",
    "Observe the original next links",
    "First: save target.next",
    "Then: predecessor.next or head takes saved next",
    "Only now release the detached target",
    "Follow the remaining links from head",
    "Save, relink, release: never use a freed node",
)


class LinkedListDeletionScene(Scene):  # type: ignore[misc]
    def construct(self) -> None:
        raw = os.environ.get(PARAMETERS_ENV)
        if raw is None:
            frames = plan_deletion(VALUES, INDEX)
        else:
            if len(raw) > 256:
                raise ValueError("animation parameters too large")
            parameters = json.loads(raw)
            if not isinstance(parameters, dict) or set(parameters) != {"values", "index"}:
                raise ValueError("invalid animation parameters")
            frames = plan_deletion(parameters["values"], parameters["index"])
        for frame, note in zip(frames, ONSCREEN_NOTES, strict=True):
            picture = self._draw_frame(frame, note)
            self.play(FadeIn(picture), run_time=0.4)
            self.wait(5.2)
            self.play(FadeOut(picture), run_time=0.4)

    def _draw_frame(self, frame: DeletionFrame, note: str) -> VGroup:
        title = Text("LINKED LIST DELETE", font_size=32).to_edge(UP)
        phase = Text(frame.stage.replace("_", " ").upper(), font_size=26).next_to(title, DOWN)
        subtitle = Text(note, font_size=19).to_edge(DOWN)
        target_id = f"n{frame.index}"
        detached = frame.stage == "relink"
        node_ids = [f"n{i}" for i in range(len(frame.original_values))
                    if frame.target_visible or i != frame.index]
        ordered = [node for node in node_ids if node != target_id] if detached else node_ids
        group = VGroup(title, phase, subtitle)
        nodes = {}
        spacing = min(1.7, 11 / max(len(ordered), 1))
        for offset, node_id in enumerate(ordered):
            number = frame.original_values[int(node_id[1:])]
            border = RoundedRectangle(width=1.1, height=0.8, corner_radius=0.14)
            border.move_to(LEFT * (spacing * (len(ordered) - 1) / 2 - spacing * offset))
            if node_id == target_id:
                border.set_color("#F4A261")
            nodes[node_id] = border
            group.add(border, Text(str(number), font_size=27).move_to(border.get_center()))
        if detached:
            border = RoundedRectangle(width=1.1, height=0.8, corner_radius=0.14)
            border.set_color("#F4A261")
            border.move_to(DOWN * 1.5 + RIGHT * 2.0)
            nodes[target_id] = border
            group.add(border, Text(str(frame.original_values[frame.index]),
                                   font_size=27).move_to(border.get_center()))
        if frame.head is None:
            group.add(Text("head -> NULL", font_size=24).move_to(LEFT * 2.5))
        else:
            head = Text("head", font_size=22).next_to(nodes[frame.head], LEFT, buff=0.8)
            group.add(head, Arrow(head.get_right(), nodes[frame.head].get_left(), buff=0.08))
        for source, target in frame.links:
            if source not in nodes:
                continue
            if target is None:
                null = Text("NULL", font_size=21).next_to(nodes[source], RIGHT, buff=0.65)
                group.add(null, Arrow(nodes[source].get_right(), null.get_left(), buff=0.08))
                continue
            if target not in nodes:
                raise ValueError("link to a released node")
            start, end = nodes[source].get_right(), nodes[target].get_left()
            if detached and source == target_id:
                start, end = nodes[source].get_top(), nodes[target].get_bottom()
            group.add(Arrow(start, end, buff=0.12, color="#2A9D8F"))
        if frame.show_saved:
            successor = "NULL" if frame.saved_successor is None else str(
                frame.original_values[int(frame.saved_successor[1:])]
            )
            saved = Text(f"saved next = {successor}", font_size=24).move_to(DOWN * 2.3)
            group.add(saved)
        return group
