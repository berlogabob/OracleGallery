"""The three screens, named after what the operator is doing.

The tabs used to be CONNECTION, CALIBRATION, TESTS, WORK, EXHIBITION, GENERATIVE, IMAGE --
the module list, which is to say this machine's P&ID. ISA-101 puts it plainly: displays are
organised by task analysis, "not on P&IDs". None of those seven names is a thing an operator
does; "work" in particular predicted nothing at all.

Three remain, and each is a phase of the job:

    PRINT   the run. What you watch while the machine draws, and where you start it.
    CREATE  authoring what gets drawn -- sketch, texture, image, text.
    SETUP   getting the machine right. Used before a run, rarely during one.

Connecting, homing and zeroing are on none of them: they live in the machine rail, reachable
from every screen, because bringing the machine up is one continuous job and used to be a
scavenger hunt across four tabs.

This module composes the existing workspace builders rather than reimplementing them, so the
move can be reviewed for equivalence: every ctx.fields and ctx.*_labels key each workspace
registered before, it still registers. The workspaces contribute plain columns now and the
screen owns the one scrolling container, so stacking three of them does not create three
independent scroll areas.
"""

from __future__ import annotations

from nicegui import ui

from .context import GuiContext
from .workspaces import calibration, connection, exhibition, generative, image, tests, work


def build_print(ctx: GuiContext) -> None:
    """The run: start it, and read whether it is going well."""
    with ui.column().classes("workspace-scroll gap-2"):
        exhibition.build(ctx)
        work.build_run(ctx)


def build_create(ctx: GuiContext) -> None:
    """Authoring a source. Every one of these ends at the same print pipeline."""
    with ui.column().classes("workspace-scroll gap-2"):
        generative.build(ctx)
        image.build(ctx)


def build_setup(ctx: GuiContext) -> None:
    """Getting the machine right, with the rarely-touched parts folded away.

    Diagnostics and commissioning are collapsed rather than deleted: they are needed on site
    and occasionally urgent, but they are not what an operator opens this screen for.
    """
    with ui.column().classes("workspace-scroll gap-2"):
        connection.build(ctx)
        calibration.build(ctx)
        tests.build(ctx)
        with ui.expansion("Diagnostics", icon="build").classes("w-full oracle-card compact-card"):
            work.build_diagnostics(ctx)
