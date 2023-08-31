"""
MOrg

A future proof opinionated software to manage your life in plaintext :
todo, agenda, journal and notes.
"""
import logging
__author__ = "Benoît HERVIER"
__copyright__ = "Copyright 2022, Benoît HERVIER"
__license__ = "MIT"
__version__ = "0.4.0"
__email__ = "b@rvier.fr"
__status__ = "Developpment"

import datetime
import os
import re
import time
from functools import partial
from pathlib import Path

import kivy
from kivy.app import App
from kivy.clock import Clock
from kivy.core.text import LabelBase
from kivy.core.window import Window
from kivy.lang import Builder
from kivy.properties import (DictProperty,
                             BooleanProperty,
                             ListProperty, NumericProperty,
                             ObjectProperty, StringProperty)
from kivy.utils import platform
from styles import GithubStyle, GruvboxDarkStyle
from models import Item, Note, Journal, Event, Todo
from ux import get_android_vkeyboard_height
from kivy.factory import Factory

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


def orgpath():
    if platform == "android":
        from android import mActivity

        context = mActivity.getApplicationContext()
        return context.getExternalFilesDir(None).getPath()

    return os.path.expanduser("~/Org")


logging.basicConfig(filename='%s/debug.log' % orgpath(), level=logging.DEBUG,
                    format='%(asctime)s %(levelname)s %(name)s %(message)s')
logger = logging.getLogger(__name__)


class MOrgApp(App):
    theme = DictProperty({
        'background': (1, 1, 1, 1),
        'header_background': (.9, .9, .9, 1),
        'primary': (0, 0, 0, 1),
        'accent': (1, 0, 0, 1),
        'accent_background': (.8, .8, .8, 1),
        'second_accent': (1, .2, 1, 1),
        'selected_accent_background': (1, 1, 1, 1),
        'todo': (0, 0, 0, 1),
        'event': (0, 0, 0, 1),
        'journal': (0, 0, 0, 1),
        'event': (0, 0, 0, 1),
        'journal': (0, 0, 0, 1),
        'note': (0, 0, 0, 1),
        'listitem_selected_background': (1, 1, 1, 1),
        'listitem_background': (1, 1, 1, 1),
        'listitem_icon': (0, 0, 0, 1),
        'listitem_selected_icon': (0, 0, 0, 1),
        'listitem': (0, 0, 0, 1),
        'listitem_selected': (0, 0, 0, 1),
        'listitem_sub': (0, 0, 0, 1),
        'listitem_selected_sub': (0, 0, 0, 1),
        'editor_background': (1, 1, 1, 1),
        'editor_text': (0, 0, 0, 1),
        'editor_pygments_style': GithubStyle,
    })

    current_date = ObjectProperty(datetime.datetime.now().date(), rebind=True)
    current_items = ListProperty([])
    current_prefix = StringProperty()
    keyboard_height = NumericProperty(0)

    picker_datetime = ObjectProperty(datetime.datetime.now())
    notes_cache = ListProperty([])
    filtered_notes = ListProperty([])

    darkmode = BooleanProperty(False)

    noteView = None

    event_busy_days = ListProperty([])
    journal_busy_days = ListProperty([])

    todos = {"A": [], "B": [], "C": []}
    events = {}
    journals = {}
    notes = {}

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
        elif modifier == ['ctrl'] and codepoint == 'k':
            print('on_keyboard', window, key, scancode, codepoint, modifier)
            Factory.NoteSearch().open()

        return False

    def build(self):
        if platform == "android":
            from kvdroid.tools.darkmode import dark_mode

        try:
            print("DARK MODE ? %s" % dark_mode())
            self.darkmode = dark_mode()
        except Exception as err:
            self.darkmode = True
            print(err)
        self.set_darkmode(self.darkmode)
        self.mainWidget = Builder.load_file("main.kv")

        Window.bind(on_keyboard=self.key_input)

        Clock.schedule_once(self.__init__later__, 0)
        return self.mainWidget

    def __init__later__(self, dt, **kv):
        print("INIT LATER")
        get_android_vkeyboard_height()
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
                Clock.schedule_once(self.load, 0)

            except Exception as err:
                print(err)

        else:
            Clock.schedule_once(self.load, 0)

        # Horrible workarround on android where sometime py intepreter return FileNotFoundError
        # reason or maybe permission not yet ack
        # while True:
        #    try:
        #        self.load()
        #        break
        #    except FileNotFoundError as err:
        #        print("INIT LATER {}".format(err))
        #        time.sleep(0.1)
        #        raise err
        #        continue

    def __go_to_line__(self, lineno, dts=None):
        # col, row = self.noteView.ids.w_textinput.get_cursor_from_index(idx)
        # print("__go_to_line__", idx, col, row)
        print(lineno)
        if lineno is None:
            return
        self.noteView.ids.w_textinput.focus = True
        self.noteView.ids.w_textinput.cursor = (0, lineno)

    def insert_text(self, text):
        self.noteView.ids.w_textinput.insert_text(text)

    def search_text(self, text):
        res = []
        for idx, item in self.current_items:
            pth = item.path
            print(pth)
            try:
                with open(pth, 'r') as fh:
                    for lineno, line in enumerate(fh.readlines()):
                        if text in line.lower():
                            res.append(
                                (os.path.relpath(pth, orgpath()), idx, lineno, line))
            except UnicodeDecodeError:
                continue
        return res

    def search_text_file(self, text):
        res = []
        text = text.lower()
        for (dpath, dnames, filenames) in os.walk(orgpath()):
            for f in filenames:
                if not f.endswith('.txt') and not f.endswith('.md'):
                    continue
                pth = os.path.join(dpath, f)
                try:
                    with open(pth, 'r') as fh:
                        for idx, line in enumerate(fh.readlines()):
                            if text in line.lower():
                                res.append(
                                    (os.path.relpath(pth, orgpath()), idx, line))
                except UnicodeDecodeError:
                    continue
        return res

    def load_events(self):
        events = {}
        pth = os.path.join(orgpath(), "agenda.txt")
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
                            dts = datetime.datetime.strptime(
                                strstart, TIME_FMT)
                            when = datetime.datetime.combine(
                                dt.date(), dts.time())
                        except (ValueError, AttributeError, TypeError):
                            when = dt
                        try:
                            dte = datetime.datetime.strptime(strend, TIME_FMT)
                            end = datetime.datetime.combine(
                                dt.date(), dte.time())
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

    def delete_current_note(self):
        print("Delete current note")
        self.root.current = "main"
        os.remove(self.noteView.filepath)
        self.load()

    def rename_current_note(self, new_note):
        print("Rename current note {}".format(new_note))
        # TODO
        print(self.noteView.filepath, os.path.join(orgpath(), new_note))

    def load_journals(self):
        journals = {}
        pth = os.path.join(orgpath(), "journal")
        if not os.path.exists(pth):
            os.makedirs(pth)
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

    def check_storage_folder(self):
        if not os.path.exists(orgpath()):
            os.makedirs(orgpath())
        if not os.path.exists(os.path.join(orgpath(), 'notes')):
            os.makedirs(os.path.join(orgpath(), 'notes'))

    def load_todos(self):
        donetxt = pytodotxt.TodoTxt(os.path.join(orgpath(), "done.txt"))
        todotxt = pytodotxt.TodoTxt(os.path.join(orgpath(), "todo.txt"))

        try:
            todotxt.parse()
        except FileNotFoundError:
            from pathlib import Path
            Path(os.path.join(orgpath(), "todo.txt")).touch()

        try:
            donetxt.parse()
        except FileNotFoundError:
            from pathlib import Path
            Path(os.path.join(orgpath(), "done.txt")).touch()

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
                    path=os.path.join(orgpath(), "todo.txt"),
                    lineno=task.linenr + 1,
                    priority=task.priority,
                )
                if (t.priority is None) or (t.priority == "A"):
                    todos["A"].append(t)
                else:
                    todos["B"].append(t)
        return todos

    def load(self, *kwargs
             ):
        self.check_storage_folder()

        self.todos = self.load_todos()
        self.events = self.load_events()
        self.journals = self.load_journals()
        self.notes.clear()
        self.notes_cache.clear()

        for i in self.events.keys():
            d = i.strftime("%Y%m") + str(i.day)
            if d not in self.event_busy_days:
                self.event_busy_days.append(d)

        for i in self.journals.keys():
            d = i.strftime("%Y%m") + str(i.day)
            if d not in self.journal_busy_days:
                self.journal_busy_days.append(d)

        for path, dirs, files in os.walk(os.path.join(orgpath(), "notes")):
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
                        self.notes_cache.append(os.path.join(
                            os.path.relpath(path, orgpath()), file))
                    except KeyError:
                        self.notes[path] = [
                            Note(
                                description=file,
                                path=os.path.join(path, file),
                            ),
                        ]
        self.filter_notesrv(None)

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
                with (open(os.path.join(orgpath(), "todo.txt"), "a")) as fh:
                    fh.write("%s\n" % self.root.ids.append_input.text)
            elif self.root.ids.append_event.state == "down":
                with (open(os.path.join(orgpath(), "agenda.txt"), "a")) as fh:
                    fh.write(
                        "\n{:%Y-%m-%d %H:%M} {}\n".format(
                            self.picker_datetime, self.root.ids.append_input.text
                        )
                    )
            elif self.root.ids.append_journal.state == "down":
                with (
                    open(
                        os.path.join(
                            orgpath(),
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
                            orgpath(),
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
                            orgpath(),
                            "quicknote.txt",
                        ),
                        "a",
                    )
                ) as fh:
                    fh.write("%s\n" % (self.root.ids.append_input.text,))
            elif self.root.ids.append_note.state == "down":
                pth = os.path.join(
                    orgpath(),
                    "notes",
                    re.sub(r"[^0-9a-zA-Z]+", "_",
                           self.root.ids.append_input.text) + ".md",
                )
                Path(pth).touch()
                self.current_items.append(
                    Note(
                        description=pth,
                        path=pth,
                    ).toDict()
                )
                Clock.schedule_once(
                    partial(self.edit, len(self.current_items) - 1, True), 0.2
                )
                return

        self.root.transition.direction = "right"
        self.root.current = "main"
        self.load()

    def filter_notesrv(self, text, *kw):
        if not text:
            self.filtered_notes = [{"text": t} for t in self.notes_cache]
        else:
            text = text.lower()
            self.filtered_notes = [{"text": x}
                                   for x in self.notes_cache if text in x.lower()]

    def filter_notesearch(self, text, *kw):
        if not text:
            self.filtered_notes = [{"text": t} for t in self.notes_cache]
        else:
            text = text.lower()
            self.filtered_notes = [{"text": x, "smalltext": "In title"}
                                   for x in self.notes_cache if text in x.lower()]
            try:
                self.filtered_notes += [{"text": x[0],
                                         "smalltext": "(Line {}) : {}".format(x[2], x[3]),
                                         "lineno": x[2], "idx": x[1]}
                                        for x in self.search_text(text)]
            except Exception:
                pass

    def edit_at(self, index, focus, lineno):
        # self.current_items[index]["lineno"] = lineno
        pth = os.path.join(orgpath(), app.filtered_notes[index]['text'])
        for idx, item in enumerate(self.current_items):
            if 'path' not in item:
                continue
            if item['path'] == pth:
                print("edit")
                self.edit(idx, focus, False)
                print(dir(self.root.ids), self.root.ids)

                return

    def edit(self, index, focus, selected):
        if "path" not in self.current_items[index]:
            return
        if self.current_items[index]["itemtype"] == 0:
            return

        self.root.transition.direction = "left"
        self.root.current = "editor"

        print("DEBUG %s" % self.current_items[index])
        pth = self.current_items[index]["path"]
        try:
            mtime = os.path.getmtime(pth)
        except FileNotFoundError:
            mtime = 0

        note = {
            "title": os.path.splitext(os.path.basename(pth))[0],
            "category": os.path.dirname(os.path.relpath(pth, orgpath())),
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

        if focus:
            try:
                Clock.schedule_once(
                    partial(self.__go_to_line__,
                            self.current_items[index]["lineno"]),
                    0.2,
                )
            except KeyError as err:
                print(err, self.current_items[index])

    def save_note(self, filepath, content):
        if self.stop_events:
            return

        with open(self.noteView.filepath, "wb") as fh:
            fh.write(content.encode("utf-8"))

    def del_note(self, note_index):
        path = os.path.join(
            self.notes_fn, self.notes[note_index]["title"] + ".md")
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
            self.theme = {
                'background': rgba(40, 40, 40, 1),
                'header_background': (0.1, 0.1, 0.1, 1),
                'primary': (1, 1, 1, 1),
                'accent': (1, 0, 0, 1),
                'accent_background': (0.2, 0.2, 0.2, 1),
                'second_accent': (1, 0.2, 1, 1),
                'second_accent_background': rgba(28, 146, 236, 1),
                'todo': rgba(214, 93, 14, 1),
                'journal': rgba(104, 157, 106, 1),
                'event': rgba(215, 153, 33, 1),
                'note': rgba(124, 111, 100, 1),
                'selected_accent_background': (1, 1, 1, 0.2),
                'listitem_selected_background': (0, 0, 0, 0),
                'listitem_background': (0, 0, 0, 0),
                'listitem_icon': (1, 1, 1, 1),
                'listitem_selected_icon': (1, 1, 1, 1),
                'listitem': (1, 1, 1, 1),
                'listitem_selected': (1, 1, 1, 1),
                'listitem_sub': (.9, 0.9, 0.9, 1),
                'listitem_selected_sub': (1, 1, 1, 1),
                'editor_background': (0.1, 0.1, 0.1, 1),
                'editor_text': (1, 1, 1, 1),
                'editor_pygments_style': GruvboxDarkStyle
            }
        else:
            self.theme = {
                'background': rgba(255, 255, 255, 1),
                'header_background': rgba(245, 245, 245, 1),
                'primary': (0, 0, 0, 1),
                'accent': rgba(214, 93, 14, 1),
                'accent_background': (0.8, 0.8, 0.8, 1),
                'second_accent': rgba(214, 154, 33, 1),
                'second_accent_background': rgba(28, 146, 236, 1),
                'todo': rgba(214, 93, 14, 1),
                'journal': rgba(104, 157, 106, 1),
                'event': rgba(215, 153, 33, 1),
                'note': rgba(124, 111, 100, 1),
                'selected_accent_background': rgba(69, 133, 136, 0.2),
                'listitem_selected_background': (1, 1, 1, 1),
                'listitem_background': (1, 1, 1, 1),
                'listitem_icon': rgba(206, 155, 113, 1),
                'listitem_selected_icon': rgba(206, 155, 1113, 1),
                'listitem': (0, 0, 0, 1),
                'listitem_selected': (.1, .1, .1, 1),
                'listitem_sub': (.1, 0.1, 0.1, 1),
                'listitem_selected_sub': (1, 1, 1, 1),
                'editor_background': (1, 1, 1, 1),
                'editor_text': (0, 0, 0, 1),
                'editor_pygments_style': GithubStyle
            }

    def touch(self, filename):
        p = os.path.join(orgpath(), filename)
        if not os.path.exists(p):
            open(p, "a").close()

    def _load_current_org_items(self, d):
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

        self.touch("expense.txt")

        for name in [
            "agenda.txt",
            "todo.txt",
            "done.txt",
            "expense.txt",
        ]:

            self.current_items.append(
                Note(
                    description=name,
                    path=os.path.join(orgpath(), name),
                ).toDict()
            )

    def _load_current_notes_items(self):
        try:
            for k in sorted(self.notes.keys()):

                self.current_items.append(
                    Item(
                        description=os.path.relpath(k, orgpath()),
                        path=None,
                        lineno=None,
                    ).toDict()
                )
                for n in sorted(self.notes[k],
                                key=lambda x: x.modified,
                                reverse=True):
                    self.current_items.append(n.toDict())
        except KeyError:
            pass

    def on_current_date(self, s, d, **kw):
        self.current_prefix = self.current_date.strftime("%Y%m")
        self.root.ids.scrollview.scroll_y = 1
        self.current_items.clear()

        self._load_current_org_items(d)
        self._load_current_notes_items()

    def on_start(self):
        pass

    def on_stop(self):
        pass


if __name__ == "__main__":
    LabelBase.register(
        name="awesome", fn_regular="data/font_awesome_5_free_solid_900.otf"
    )
    app = MOrgApp()
    try:
        app.run()
    except Exception as err:
        logger.error(err)
