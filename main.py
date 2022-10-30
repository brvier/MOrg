"""
MOrg

A future proof opinionated software to manage your life in plaintext : todo, agenda, journal and notes.
"""
__author__ = "Benoît HERVIER"
__copyright__ = "Copyright 2022, Benoît HERVIER"
__license__ = "MIT"
__version__ = "0.2.0"
__email__ = "b@rvier.fr"
__status__ = "Developpment"

import datetime
import os
import re
import time
from functools import partial

import humanize
import kivy
from kivy.app import App
from kivy.clock import Clock
from kivy.core.text import LabelBase
from kivy.core.window import Window
from kivy.lang import Builder
from kivy.properties import ColorProperty  # DictProperty,
from kivy.properties import (BooleanProperty, ListProperty, NumericProperty,
                             ObjectProperty, StringProperty)
from kivy.uix.behaviors import (ButtonBehavior, FocusBehavior,
                                ToggleButtonBehavior)
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.codeinput import CodeInput  # noqa
from kivy.uix.label import Label
from kivy.uix.recycleboxlayout import RecycleBoxLayout
from kivy.uix.recycleview import RecycleView
from kivy.uix.recycleview.layout import LayoutSelectionBehavior
from kivy.uix.recycleview.views import RecycleDataViewBehavior
from kivy.uix.screenmanager import Screen
from kivy.uix.textinput import TextInput
from kivy.utils import platform
from kivy.vector import Vector
from pygments.lexers.textfmts import TodotxtLexer

from styles import GithubStyle, GruvboxDarkStyle

if platform == "android":
    import android

import pytodotxt

kivy.require("2.0.0")
Window.softinput_mode = ""
vkeyboard_offset = 0

EVENT_RE = re.compile(
    r"^([\d]{4}-[\d]{2}-[\d]{2})\s([\d]{2}:[\d]{2})?\s?([\d]{2}:[\d]{2})?\s?(.*)$",
    re.ASCII,
)
TIME_FMT = "%H:%M"
DATE_FMT = "%Y-%m-%d"


def rgba(r, g, b, a):
    return r / 255, g / 255, b / 255, a


def get_android_vkeyboard_height():
    print("get_android_vkeyboard_height")
    global vkeyboard_offset
    if platform == "android":
        # for a unknow reason keyboard height can be negative when closed... and
        # an offset persists when open : dirty work arround
        h = android.get_keyboard_height()
        print(h)
        if not vkeyboard_offset:
            if h < 0:
                vkeyboard_offset = -h
                h = 0
        return h + vkeyboard_offset
    else:
        return Window.keyboard_height


class Item:
    description = None
    path = None
    itemtype = 0
    lineno = 0

    def __init__(self, description, path, lineno):
        self.description = description
        self.path = path
        self.itemtype = 0
        self.lineno = lineno

    def toDict(self):
        return {
            "description": self.description,
            "itemtype": 0,
        }


class Todo(Item):
    priority = None

    def __init__(self, description, path="todo.txt", lineno=0, priority=None):
        super(Todo, self).__init__(description, path, lineno)
        self.priority = priority

    def toDict(self):
        return {
            "description": self.description,
            "priority": self.priority,
            "path": self.path,
            "lineno": self.lineno,
            "itemtype": 1,
        }


class CircularButton(
    ButtonBehavior,
    Label,
):
    def collide_point(self, x, y):
        return Vector(x, y).distance(self.center) <= self.width / 2


class Event(Item):
    when = None
    end = None

    def __init__(self, description, when, path="agenda.txt", lineno=0, end=None):
        super(Event, self).__init__(description, path, lineno)
        self.when = when
        self.end = end

    def toDict(self):

        return {
            "description": self.description,
            "when": self.when.strftime("%Y-%m-%d %H:%M"),
            "time": self.when.strftime("%H:%M"),
            "end": self.end.strftime("%Y-%m-%d %H:%M") if self.end else "",
            "path": self.path,
            "lineno": self.lineno,
            "itemtype": 2,
        }


class Journal(Item):
    when = None

    def __init__(self, description, path, when, lineno=0):
        super(Journal, self).__init__(description, path, lineno)
        self.when = when
        self.description = description.strip("\n ")

    def toDict(self):
        return {
            "description": self.description,
            "when": self.when.strftime("%Y-%m-%d %H:%M"),
            "path": self.path,
            "lineno": self.lineno,
            "itemtype": 3,
        }


class Expense(Item):
    when = None

    def __init__(self, description, when, path="expense.txt", lineno=0):
        super(Expense, self).__init__(description, path, lineno)
        self.when = when


class Note(Item):
    category = None
    modified = None

    def __init__(self, description, path):
        super(Note, self).__init__(description, path, lineno=0)
        self.modified = os.path.getmtime(path)
        self.category = os.path.dirname(path)

    def toDict(self):
        return {
            "description": self.description,
            "modified": humanize.naturaltime(
                datetime.datetime.fromtimestamp(self.modified)
            ),
            "category": self.category,
            "path": self.path,
            "itemtype": 4,
        }


class DatePicker(BoxLayout):
    pass


class SelectableRecycleBoxLayout(
    FocusBehavior, LayoutSelectionBehavior, RecycleBoxLayout
):
    """Adds selection and focus behaviour to the view."""


class ToggleLabel(ToggleButtonBehavior, Label):
    active = BooleanProperty(False)

    def __init__(self, **kwargs):
        super(ToggleLabel, self).__init__(**kwargs)

        self.allow_no_selection = False
        self.group = "default"


class MOrgRecycleView(RecycleView):
    def __init__(self, **kwargs):
        super(MOrgRecycleView, self).__init__(**kwargs)


class MOrgListItem(RecycleDataViewBehavior, ButtonBehavior, BoxLayout):

    index = None
    selected = BooleanProperty(False)
    selectable = BooleanProperty(True)
    line = StringProperty()
    description = StringProperty()
    when = StringProperty(rebind=True)
    end = StringProperty(rebind=True)
    priority = StringProperty(None)
    path = StringProperty()
    sortkey = None
    itemtype = NumericProperty(0)  # 0 header, 1 todo, 2 event, 3 journal, 4 note
    filename = StringProperty()
    modified = StringProperty()

    def __init__(self, **kwargs):
        super(MOrgListItem, self).__init__(**kwargs)

    def refresh_view_attrs(self, rv, index, data):
        """Catch and handle the view changes"""
        self.index = index
        return super(MOrgListItem, self).refresh_view_attrs(rv, index, data)

    def on_touch_down(self, touch):
        """Add selection on touch down"""
        if super(MOrgListItem, self).on_touch_down(touch):
            return True
        if self.collide_point(*touch.pos) and self.selectable:
            return self.parent.select_with_touch(self.index, touch)

    def apply_selection(self, rv, index, is_selected):
        """Respond to the selection of items in the view."""
        self.selected = is_selected
        if is_selected:
            self.parent.clear_selection()


class MTextInput(TextInput):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # User can change keyboard size during input
        # so we should regularly update the keyboard height
        self.trigger_keyboard_height = Clock.create_trigger(
            self.update_keyboard_height, 0.2, interval=True
        )
        self.trigger_cancel_keyboard_height = Clock.create_trigger(
            lambda dt: self.trigger_keyboard_height.cancel(), 1.0, interval=False
        )

    def update_keyboard_height(self, dt):
        if platform == "android":
            App.get_running_app().keyboard_height = get_android_vkeyboard_height()

    def _bind_keyboard(self):
        super()._bind_keyboard()
        if platform == "android":
            self.trigger_cancel_keyboard_height.cancel()
            self.trigger_keyboard_height()

    def _unbind_keyboard(self):
        super()._unbind_keyboard()
        if platform == "android":
            self.trigger_cancel_keyboard_height()


class Page(Screen):
    pass


class NoteView(Page):

    title = StringProperty()
    content = StringProperty()
    last_modification = StringProperty()
    mtime = NumericProperty()
    filepath = StringProperty()


class MDInput(CodeInput):

    re_indent_todo = re.compile(r"^\s*(-\s\[\s\]\s)")
    re_indent_done = re.compile(r"^\s*(-\s\[x\]\s)")
    re_indent_list = re.compile(r"^\s*(-\s)")

    def __init__(self, **kwarg):
        CodeInput.__init__(self, lexer=TodotxtLexer(), style_name="default")
        # User can change keyboard size during input,
        # so we should regularly update the keyboard height
        self.trigger_keyboard_height = Clock.create_trigger(
            self.update_keyboard_height, 0.2, interval=True
        )
        self.trigger_cancel_keyboard_height = Clock.create_trigger(
            lambda dt: self.trigger_keyboard_height.cancel(), 1.0, interval=False
        )

    def update_keyboard_height(self, dt):
        if platform == "android":
            App.get_running_app().keyboard_height = get_android_vkeyboard_height()

    def _bind_keyboard(self):
        super()._bind_keyboard()
        if platform == "android":
            self.trigger_cancel_keyboard_height.cancel()
            self.trigger_keyboard_height()

    def _unbind_keyboard(self):
        super()._unbind_keyboard()
        if platform == "android":
            self.trigger_cancel_keyboard_height()

    def set_cursor(self, idx):
        self.cursor = self.get_cursor_from_index(idx)
        self.focus = True

    def do_indent(self, *kwargs):
        index = self.cursor_index()
        if index > 0:
            _text = self.text
            line_start = _text.rfind("\n", 0, index)
            self.text = _text[: line_start + 1] + "  " + _text[line_start + 1 :]
            if index > line_start:
                index += 2

        self.set_cursor(index)

    def do_unindent(self, *kwargs):
        index = self.cursor_index()
        _text = self.text
        line_start = _text.rfind("\n", 0, index)
        line_end = _text.find("\n", index)
        if line_end == -1:
            line_end = len(_text)
        if (_text[line_start + 1 : line_start + 3]) == "  ":
            self.text = _text[: line_start + 1] + _text[line_start + 3 :]
            if index > line_start:
                index -= 2
        self.set_cursor(index)

    def do_todo(self):
        index = self.cursor_index()

        if index >= 0:
            _text = self.text
            line_start = _text.rfind("\n", 0, index)
            line_end = _text.find("\n", index)
            if line_end == -1:
                line_end = len(_text)
            if line_start < 0:
                line_start = -1

            print(type(self.lexer))

            if type(self.lexer) == TodotxtLexer:
                if _text[line_start + 1 : line_start + 3] == "x ":
                    self.text = "{}{}{}".format(
                        self.text[: line_start + 1],
                        "",
                        self.text[line_start + 3 :],
                    )
                else:
                    self.text = "{}{}{}".format(
                        self.text[: line_start + 1],
                        "x ",
                        self.text[line_start + 1 :],
                    )

                self.set_cursor(index + (len(self.text) - len(_text)))

                return
            idx = _text.find("- [ ]", line_start + 1, line_end)
            if idx >= 0:
                self.text = "{}{}{}".format(
                    self.text[: idx + 3],
                    "x",
                    self.text[idx + 4 :],
                )
            else:
                idx = _text.find("- [x]", line_start + 1, line_end)
                if idx >= 0:
                    self.text = "{}{}{}".format(
                        self.text[:idx],
                        "- ",
                        self.text[idx + 6 :],
                    )
                else:
                    idx = _text.find("- ", line_start + 1, line_end)
                    if idx >= 0:
                        self.text = "{}{}{}".format(
                            self.text[:idx],
                            "- [ ] ",
                            self.text[idx + 2 :],
                        )
                    else:
                        self.text = "{}{}{}".format(
                            self.text[: line_start + 1],
                            "- ",
                            self.text[line_start + 1 :],
                        )
            self.set_cursor(index + (len(self.text) - len(_text)))

    def insert_text(self, substring, from_undo=False):
        if not from_undo and self.multiline and self.auto_indent and substring == "\n":
            substring = self._auto_indent(substring)
        CodeInput.insert_text(self, substring, from_undo)

    def _auto_indent(self, substring):
        index = self.cursor_index()

        if index > 0:
            _text = self.text
            line_start = _text.rfind("\n", 0, index)
            if line_start > -1:
                line = _text[line_start + 1 : index]  # noqa:E203
                indent = self.re_indent_todo.match(line)

                if indent is None:
                    indent = self.re_indent_done.match(line)
                if indent is None:
                    indent = self.re_indent_list.match(line)
                if indent is not None:
                    substring += indent.group().replace("x", " ")
        return substring


class MOrgApp(App):
    bg_color = ColorProperty([1, 1, 1, 1])
    header_bg_color = ColorProperty([0.9, 0.9, 0.9, 1])
    primary_color = ColorProperty([0, 0, 0, 1])
    accent_color = ColorProperty([1, 0, 0, 1])
    accent_bg_color = ColorProperty([0.8, 0.8, 0.8, 1])
    second_accent_color = ColorProperty([1, 0.2, 1, 1])
    second_accent_color = ColorProperty([1, 0.2, 1, 1])
    selected_accent_bg_color = ColorProperty([1, 1, 1, 1])
    todo_color = ColorProperty([0, 0, 0, 1])
    event_color = ColorProperty([0, 0, 0, 1])
    journal_color = ColorProperty([0, 0, 0, 1])
    note_color = ColorProperty([0, 0, 0, 1])
    listitem_selected_bgcolor = ColorProperty([1, 1, 1, 1])
    listitem_bgcolor = ColorProperty([1, 1, 1, 1])
    listitem_icon_color = ColorProperty([0, 0, 0, 1])
    listitem_selected_icon_color = ColorProperty([0, 0, 0, 1])
    listitem_color = ColorProperty([0, 0, 0, 1])
    listitem_selected_color = ColorProperty([0, 0, 0, 1])
    listitem_subcolor = ColorProperty([0, 0, 0, 1])
    listitem_selected_subcolor = ColorProperty([0, 0, 0, 1])
    editor_bgcolor = ColorProperty([1, 1, 1, 1])
    editor_textcolor = ColorProperty([0, 0, 0, 1])
    editor_pygments_style = GithubStyle
    current_date = ObjectProperty(datetime.datetime.now().date(), rebind=True)
    current_items = ListProperty([])
    current_prefix = StringProperty()
    keyboard_height = NumericProperty(0)
    picker_datetime = ObjectProperty(datetime.datetime.now())

    darkmode = BooleanProperty(False)

    noteView = None

    event_busy_days = ListProperty([])
    journal_busy_days = ListProperty([])

    todos = {"A": [], "B": [], "C": []}
    events = {}
    journals = {}
    notes = {}

    @property
    def orgpath(self):
        if platform == "android":
            return "/sdcard/Android/data/fr.rvier.morg/files/"
        return os.path.expanduser("~/Org")

    def key_input(self, window, key, scancode, codepoint, modifier):
        # key == 27 means it is waiting for
        # back button tobe pressed
        if key == 27:
            # checking if we are at mainscreen or not
            if self.root.current == "main":
                # return True means do nothing
                return False
            else:
                # self.root.transition.direction = "right"
                self.root.current = "main"
                self.load()
                return True
        return False

    def build(self):
        if platform == "android":
            from kvdroid.tools.darkmode import dark_mode

        try:
            print("DARK MODE ? %s" % dark_mode())
            self.darkmode = dark_mode()
        except Exception as err:
            self.darkmode = False
            print(err)
        self.set_darkmode(self.darkmode)
        self.mainWidget = Builder.load_file("main.kv")

        Window.bind(on_keyboard=self.key_input)

        Clock.schedule_once(self.__init__later__, 0)
        return self.mainWidget

    def __init__later__(self, dt, **kv):
        print("INIT LATER")
        if platform == "android":
            from android.permissions import Permission, request_permissions

            try:

                request_permissions(
                    [
                        Permission.READ_EXTERNAL_STORAGE,
                        Permission.WRITE_EXTERNAL_STORAGE,
                    ]
                )
                # app_folder = os.path.dirname(os.path.abspath(__file__))

            except Exception as err:
                print(err)

        # Horrible workarround on android where sometime py intepreter return FileNotFoundError
        # reason or maybe permission not yet ack

        while True:
            try:
                self.load()
                break
            except FileNotFoundError:
                time.sleep(0.1)
                continue

    def __go_to_line__(self, lineno, dts=None):
        # col, row = self.noteView.ids.w_textinput.get_cursor_from_index(idx)
        # print("__go_to_line__", idx, col, row)
        print(lineno)
        self.noteView.ids.w_textinput.focus = True
        self.noteView.ids.w_textinput.cursor = (0, lineno)

    def load_events(self):
        events = {}
        pth = os.path.join(self.orgpath, "agenda.txt")
        try:
            is_sorted = False
            with open(pth, "r") as fh:
                original_lines = fh.readlines()
                lines = sorted(original_lines)
                if lines != original_lines:
                    is_sorted = True
                for lineno, line in enumerate(lines):
                    g = EVENT_RE.match(line)
                    if g:
                        strdate, strstart, strend, description = g.groups()
                        dt = datetime.datetime.strptime(strdate, DATE_FMT)
                        try:
                            dts = datetime.datetime.strptime(strstart, TIME_FMT)
                            when = datetime.datetime.combine(dt.date(), dts.time())
                        except (ValueError, AttributeError, TypeError):
                            when = dt
                        try:
                            dte = datetime.datetime.strptime(strend, TIME_FMT)
                            end = datetime.datetime.combine(dt.date(), dte.time())
                        except (ValueError, AttributeError, TypeError):
                            end = None
                        e = Event(
                            description=description,
                            lineno=lineno,
                            path=pth,
                            when=when,
                            end=end,
                        )
                        try:
                            events[dt.date()].append(e)
                        except KeyError:
                            events[dt.date()] = [
                                e,
                            ]
            if is_sorted:
                with open(pth, "w") as fh:
                    fh.write("".join(lines).strip())
        except FileNotFoundError:
            open(pth, "a").close()
        return events

    def load_journals(self):
        journals = {}
        pth = os.path.join(self.orgpath, "journal")
        fs = os.listdir(pth)
        for f in fs:
            if f.startswith("."):
                continue
            with open(os.path.join(pth, f), "r") as fh:
                for lineno, line in enumerate(fh.readlines()):
                    try:
                        dt = datetime.datetime.strptime(f[:-4], "%Y-%m-%d")
                    except ValueError:
                        continue
                    j = Journal(
                        description=line,
                        lineno=lineno,
                        path=os.path.join(pth, f),
                        when=dt,
                    )
                    try:
                        journals[dt.date()].append(j)
                    except KeyError:
                        journals[dt.date()] = [
                            j,
                        ]
        return journals

    def load_todos(self):
        donetxt = pytodotxt.TodoTxt(os.path.join(self.orgpath, "done.txt"))
        todotxt = pytodotxt.TodoTxt(os.path.join(self.orgpath, "todo.txt"))

        try:
            todotxt.parse()
        except FileNotFoundError:
            open(os.path.join(self.orgpath, "todo.txt"), "a").close()

        try:
            donetxt.parse()
        except FileNotFoundError:
            open(os.path.join(self.orgpath, "done.txt"), "a").close()

        for task in todotxt.tasks:
            if task.is_completed:
                donetxt.add(task)
        todotxt.tasks = [t for t in todotxt.tasks if not t.is_completed]
        donetxt.save()
        todotxt.save()

        todos = {"A": [], "B": []}
        for task in todotxt.tasks:
            if task.description is None:
                continue
            if task.priority is None:
                task.priority = "A"
            if not task.is_completed:
                t = Todo(
                    task.description,
                    path=os.path.join(self.orgpath, "todo.txt"),
                    lineno=task.linenr,
                    priority=task.priority,
                )
                if (t.priority is None) or (t.priority == "A"):
                    todos["A"].append(t)
                else:
                    todos["B"].append(t)
        return todos

    def load(self):
        self.todos = self.load_todos()
        self.events = self.load_events()
        self.journals = self.load_journals()
        self.notes.clear()

        for i in self.events.keys():
            d = i.strftime("%y%m") + str(i.day)
            if d not in self.event_busy_days:
                self.event_busy_days.append(d)

        for i in self.journals.keys():
            d = i.strftime("%y%m") + str(i.day)
            if d not in self.journal_busy_days:
                self.journal_busy_days.append(d)

        for path, dirs, files in os.walk(os.path.join(self.orgpath, "notes")):
            dirs = [d for d in dirs if not d.startswith(".")]
            files = [f for f in files if not f.startswith(".")]
            if any([prt.startswith(".") for prt in path.split("/")]):
                continue

            for file in files:
                if file.startswith(".") or os.path.basename(path).startswith("."):
                    continue
                if file.endswith(".txt") or file.endswith(".md"):
                    try:
                        self.notes[path].append(
                            Note(
                                description=file,
                                path=os.path.join(path, file),
                            )
                        )
                    except KeyError:
                        self.notes[path] = [
                            Note(
                                description=file,
                                path=os.path.join(path, file),
                            ),
                        ]

        self.current_date = datetime.datetime.now().date()
        self.on_current_date(self, self.current_date)

    def add(self, **args):
        print(args)
        self.picker_datetime = datetime.datetime.combine(
            self.current_date, datetime.time(12, 0, 0)
        )
        self.root.transition.direction = "left"
        self.root.current = "append"
        self.root.ids.append_input.text = ""
        self.root.ids.append_input.focus = True

    def do_add(self, **args):
        print(self.root.ids)

        if self.root.ids.append_input.text:
            if self.root.ids.append_todo.state == "down":
                with (open(os.path.join(self.orgpath, "todo.txt"), "a")) as fh:
                    fh.write("%s\n" % self.root.ids.append_input.text)
            elif self.root.ids.append_event.state == "down":
                with (open(os.path.join(self.orgpath, "agenda.txt"), "a")) as fh:
                    fh.write(
                        "\n{:%Y-%m-%d %H:%M} {}\n".format(
                            self.picker_datetime, self.root.ids.append_input.text
                        )
                    )
            elif self.root.ids.append_journal.state == "down":
                with (
                    open(
                        os.path.join(
                            self.orgpath,
                            "journal",
                            "%s.txt" % datetime.datetime.now().strftime("%Y-%m-%d"),
                        ),
                        "a",
                    )
                ) as fh:
                    fh.write(
                        "%s %s\n"
                        % (
                            datetime.datetime.now().strftime("%H:%M"),
                            self.root.ids.append_input.text,
                        )
                    )
            elif self.root.ids.append_expense.state == "down":
                with (
                    open(
                        os.path.join(
                            self.orgpath,
                            "expense.txt",
                        ),
                        "a",
                    )
                ) as fh:
                    fh.write(
                        "%s %s\n"
                        % (
                            datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
                            self.root.ids.append_input.text,
                        )
                    )
            elif self.root.ids.append_quicknote.state == "down":
                with (
                    open(
                        os.path.join(
                            self.orgpath,
                            "quicknote.txt",
                        ),
                        "a",
                    )
                ) as fh:
                    fh.write("%s\n" % (self.root.ids.append_input.text,))

        self.root.transition.direction = "right"
        self.root.current = "main"
        self.load()

    def edit(self, index, selected):

        if "path" not in self.current_items[index]:
            return
        if self.current_items[index]["itemtype"] == 0:
            return

        self.root.transition.direction = "left"
        self.root.current = "editor"

        print(self.current_items[index])
        pth = self.current_items[index]["path"]
        try:
            mtime = os.path.getmtime(pth)
        except FileNotFoundError:
            mtime = 0

        note = {
            "title": os.path.splitext(os.path.basename(pth))[0],
            "category": os.path.dirname(os.path.relpath(pth, self.orgpath)),
            "last_modification": time.asctime(time.localtime(mtime)),
            "mtime": mtime,
            "content": "",
            "filepath": pth,
        }

        try:
            with open(note["filepath"], "r") as fh:
                note["content"] = fh.read()
        except Exception as err:
            print(err)

        if self.noteView is None:
            self.noteView = self.root.ids.editor

        self.stop_events = True
        self.noteView.title = note.get("title")
        self.noteView.last_modification = note.get("last_modification")
        self.noteView.filepath = note.get("filepath")
        self.noteView.content = note.get("content")
        self.stop_events = False

        self.display_toolbar = True
        self.display_add = False
        try:
            Clock.schedule_once(
                partial(self.__go_to_line__, self.current_items[index]["lineno"]), 0.1
            )
        except KeyError:
            pass

    def save_note(self, filepath, content):
        if self.stop_events:
            return

        with open(self.noteView.filepath, "wb") as fh:
            fh.write(content.encode("utf-8"))

    def del_note(self, note_index):
        path = os.path.join(self.notes_fn, self.notes[note_index]["title"] + ".md")
        print("Deleting path ", path)
        del self.notes[note_index]
        self.sync()
        self.go_notes()

    def on_darkmode(self, value, obj, **kw):
        if hasattr(self, "mainWidget"):
            print("DEBUG DARKMODE : ", self.darkmode, value)
            if platform == "android":
                from kvdroid.tools import restart_app

                restart_app()

    def on_resume(self, **kw):
        if platform == "android":
            from kvdroid.tools.darkmode import dark_mode

            try:
                self.darkmode = dark_mode()
            except Exception as err:
                print(err)

    def set_darkmode(self, value):
        # THEME
        if value is True:
            self.bg_color = rgba(40, 40, 40, 1)
            self.header_bg_color = [0.1, 0.1, 0.1, 1]
            self.primary_color = [1, 1, 1, 1]
            self.accent_color = [1, 0, 0, 1]
            self.accent_bg_color = [0.2, 0.2, 0.2, 1]
            self.second_accent_color = [1, 0.2, 1, 1]
            self.second_accent_bg_color = [28 / 255, 146 / 255, 236 / 255, 1]
            self.todo_color = rgba(214, 93, 14, 1)
            self.journal_color = rgba(104, 157, 106, 1)
            self.event_color = rgba(215, 153, 33, 1)
            self.note_color = rgba(124, 111, 100, 1)
            self.selected_accent_bg_color = [1, 1, 1, 0.2]
            self.listitem_selected_bgcolor = [0, 0, 0, 0]
            self.listitem_bgcolor = [0, 0, 0, 0]
            self.listitem_icon_color = [1, 1, 1, 1]
            self.listitem_selected_icon_color = [1, 1, 1, 1]
            self.listitem_color = [1, 1, 1, 1]
            self.listitem_selected_color = [1, 1, 1, 1]
            self.listitem_subcolor = [1, 1, 1, 1]
            self.listitem_selected_subcolor = [1, 1, 1, 1]
            self.editor_bgcolor = [0.1, 0.1, 0.1, 1]
            self.editor_textcolor = [1, 1, 1, 1]
            self.editor_pygments_style = GruvboxDarkStyle
        else:
            self.bg_color = rgba(255, 255, 255, 1)  # [1, 1, 1, 1]
            self.header_bg_color = rgba(245, 245, 245, 1)
            self.primary_color = [0, 0, 0, 1]
            self.accent_color = rgba(214, 93, 14, 1)
            self.accent_bg_color = [0.8, 0.8, 0.8, 1]
            self.second_accent_color = rgba(214, 153, 33, 1)
            self.second_accent_bg_color = [28 / 255, 146 / 255, 236 / 255, 1]
            self.todo_color = rgba(214, 93, 14, 1)
            self.journal_color = rgba(104, 157, 106, 1)
            self.event_color = rgba(215, 153, 33, 1)
            self.note_color = rgba(124, 111, 100, 1)
            self.selected_accent_bg_color = rgba(69, 133, 136, 1)
            self.listitem_selected_bgcolor = [1, 1, 1, 1]
            self.listitem_bgcolor = [1, 1, 1, 1]
            self.listitem_icon_color = [206 / 255, 155 / 255, 113 / 255, 1]
            self.listitem_selected_icon_color = [206 / 255, 155 / 255, 113 / 255, 1]
            self.listitem_color = [0, 0, 0, 1]
            self.listitem_selected_color = [0, 0, 0, 1]
            self.listitem_subcolor = [0.1, 0.1, 0.1, 1]
            self.listitem_selected_subcolor = [0.1, 0.1, 0.1, 1]
            self.editor_bgcolor = [1, 1, 1, 1]
            self.editor_textcolor = [0, 0, 0, 1]
            self.editor_pygments_style = GithubStyle

    def touch(self, filename):
        p = os.path.join(self.orgpath, filename)
        if not os.path.exists(p):
            open(p, "a").close()

    def on_current_date(self, s, d, **kw):
        self.current_prefix = self.current_date.strftime("%y%m")
        self.root.ids.scrollview.scroll_y = 1
        # filter current items from main item
        self.current_items.clear()

        try:
            for e in self.events[d]:
                self.current_items.append(e.toDict())
        except KeyError:
            pass

        try:
            for e in self.todos["A"]:
                self.current_items.append(e.toDict())
        except KeyError:
            pass

        if d in self.journals:
            self.current_items.append(
                Item(
                    description="journal",
                    path=None,
                    lineno=None,
                ).toDict()
            )

        try:
            for e in self.journals[d]:
                self.current_items.append(e.toDict())
        except KeyError:
            pass

        self.current_items.append(
            Item(
                description="org",
                path=None,
                lineno=None,
            ).toDict()
        )

        self.touch("expenses.txt")
        self.touch("quicknote.txt")

        for name in [
            "agenda.txt",
            "todo.txt",
            "done.txt",
            "expense.txt",
            "quicknote.txt",
        ]:

            self.current_items.append(
                Note(
                    description=name,
                    path=os.path.join(self.orgpath, name),
                ).toDict()
            )

        try:
            for k in sorted(self.notes.keys()):

                self.current_items.append(
                    Item(
                        description=os.path.relpath(k, self.orgpath),
                        path=None,
                        lineno=None,
                    ).toDict()
                )
                for n in sorted(self.notes[k], key=lambda x: x.modified, reverse=True):
                    self.current_items.append(n.toDict())
        except KeyError:
            pass


if __name__ == "__main__":
    LabelBase.register(
        name="awesome", fn_regular="data/font_awesome_5_free_solid_900.otf"
    )
    app = MOrgApp()
    app.run()
