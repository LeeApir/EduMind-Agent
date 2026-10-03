"""Fixed Manim scene for a singly linked list insertion; constants are data-only inputs."""

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

from app.animation_templates.insertion_plan import InsertionFrame, plan_insertion

VALUES = [1, 3, 5]
INDEX = 1
VALUE = 2
PARAMETERS_ENV = "EDUMIND_ANIMATION_PARAMETERS"
ONSCREEN_NOTES = (
    "Observe the original next links",
    "Locate the predecessor and successor",
    "First: new.next points to successor",
    "Then: predecessor.next or head points to new",
    "Follow head and next through the new list",
    "Keep this pointer update order",
)


class LinkedListInsertionScene(Scene):  # type: ignore[misc]
    def construct(self) -> None:
        raw = os.environ.get(PARAMETERS_ENV)
        if raw is None:
            frames = plan_insertion(VALUES, INDEX, VALUE)
        else:
            if len(raw) > 256:
                raise ValueError("animation parameters too large")
            parameters = json.loads(raw)
            if not isinstance(parameters, dict) or set(parameters) != {"values", "index", "value"}:
                raise ValueError("invalid animation parameters")
            frames = plan_insertion(parameters["values"], parameters["index"], parameters["value"])
        for frame, note in zip(frames, ONSCREEN_NOTES, strict=True):
            picture = self._draw_frame(frame, note)
            self.play(FadeIn(picture), run_time=0.4)
            self.wait(5.2)
            self.play(FadeOut(picture), run_time=0.4)

    def _draw_frame(self, frame: InsertionFrame, note: str) -> VGroup:
        title = Text("LINKED LIST INSERT", font_size=32).to_edge(UP)
        phase = Text(frame.stage.replace("_", " ").upper(), font_size=26).next_to(title, DOWN)
        subtitle = Text(note, font_size=19).to_edge(DOWN)
        node_ids = [f"n{i}" for i in range(len(frame.original_values))]
        saving_successor = frame.stage == "save_successor"
        if frame.visible_new and not saving_successor:
            node_ids.insert(frame.index, "new")
        elif frame.visible_new:
            node_ids.append("new")
        if not node_ids:
            empty = Text("head -> NULL", font_size=32)
            return VGroup(title, phase, empty, subtitle)
        nodes = {}
        group = VGroup(title, phase, subtitle)
        total = len(node_ids)
        spacing = min(1.7, 11 / max(total, 1))
        for offset, node_id in enumerate(node_ids):
            number = frame.value if node_id == "new" else frame.original_values[int(node_id[1:])]
            border = RoundedRectangle(width=1.1, height=0.8, corner_radius=0.14)
            border.move_to(LEFT * (spacing * (total - 1) / 2 - spacing * offset))
            if node_id == "new" and saving_successor:
                border.shift(DOWN * 1.5)
            label = Text(str(number), font_size=27).move_to(border.get_center())
            if node_id == "new":
                border.set_color("#F4A261")
            nodes[node_id] = border
            group.add(border, label)
        if frame.head is None:
            group.add(Text("head -> NULL", font_size=22).to_edge(LEFT))
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
                continue
            start = nodes[source].get_right()
            end = nodes[target].get_left()
            if saving_successor and source == "new":
                start = nodes[source].get_top()
                end = nodes[target].get_bottom()
            elif node_ids.index(source) > node_ids.index(target):
                start = nodes[source].get_bottom()
                end = nodes[target].get_bottom()
            arrow = Arrow(start, end, buff=0.12, color="#2A9D8F")
            group.add(arrow)
        return group
