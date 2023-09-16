import os.path
import humanize
import datetime


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
        super(Note, self).__init__(description, path, lineno=None)
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
            "lineno": 0,
            "itemtype": 4,
        }


class Daily(Item):
    when = None

    def __init__(self, path, when, lineno=0):
        super(Daily, self).__init__("", path, lineno)
        self.when = when
        self.description = open(self.path, 'r').read()

    def toDict(self):
        return {
            "description": self.description,
            "when": self.when.strftime("%Y-%m-%d %H:%M"),
            "path": self.path,
            "lineno": 0,
            "itemtype": 3,
        }

    def toDicts(self):
        return [{
            "description": line,
            "when": self.when.strftime("%Y-%m-%d %H:%M"),
            "path": self.path,
            "lineno": idx,
            "itemtype": 3,
        } for idx, line in enumerate(self.description.split('\n')) if line != ""]


