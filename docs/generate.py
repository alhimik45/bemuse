
# http://stackoverflow.com/questions/2186525/use-a-glob-to-find-files-recursively-in-python
import os
import re
import errno
import fnmatch
from itertools import chain

# >> docs/generate
# The code documentation and module documentations are generated by a Python
# script, ``generate.py``, which scans the source files for comment blocks
# followed by the code that matches the regular expression.
#
# This is simple and works very well, but the code must be written according
# to the coding convention.
#

# >> docs/codedoc
#
# Source code files that matches the pattern ``src/**/.js`` or ``docs/**/*.py``
# will be processed to find documentation comments.
#
def get_source_files():
    for root, dirnames, filenames in os.walk('../src'):
        for filename in fnmatch.filter(filenames, '*.js'):
            yield root + '/' + filename
    for root, dirnames, filenames in os.walk('../docs'):
        for filename in fnmatch.filter(filenames, '*.py'):
            yield root + '/' + filename

def mkpath(path):
    try:
        os.makedirs(path)
    except OSError as exc:
        if exc.errno == errno.EEXIST and os.path.isdir(path):
            pass
        else:
            raise

def indent3(x):
    return '\n'.join('   ' + line for line in x.splitlines())

CODEDOC_RE      = re.compile(r'^>> (\S+)$')
COMMENT_RE      = re.compile(r'^(?://|#)(?: (.*$)|$)')
CLASS_RE        = re.compile(r'^(?:export )?class (\w+)')
EXPORT_LET_RE   = re.compile(r'^export let (\w+)')
CONSTRUCTOR_RE  = re.compile(r'^constructor\((.*?)\) \{$')
METHOD_RE       = re.compile(r'^(\w+\(.*?\)) {$')
GETTER_RE       = re.compile(r'^get (\w+)\(\) {$')
ATTRIBUTE_RE    = re.compile(r'^this.(\w+)\s*=')
MODULE_RE       = re.compile(r'src/(.*?)\.js$')

class FileProcessor(object):

    def __init__(self, path, root):
        self.root = root
        self.path = path
        self.buffer = None

    def module_doc(self):
        match = MODULE_RE.search(self.path)
        modulename = match.group(1)
        if modulename.endswith('/index'):
            modulename = modulename[:-6]
        return self.root.module(modulename)

    def process(self):
        self.state = None
        self.current_class = None
        with open(self.path, 'r') as f:
            for line in f:
                self.current_line = line.strip()
                self.process_line()

    def match(self, regex):
        match = regex.match(self.current_line)
        self.current_match = match
        return match

    def group(self, group):
        return self.current_match.group(group)

    def process_line(self):
        if self.match(COMMENT_RE):
            if self.buffer is None: self.buffer = []
            self.buffer.append(self.group(1) or '')
        elif self.buffer is not None:
            self.post_state = None
            self.process_post_comment()
            self.buffer = None

    def process_post_comment(self):
        if self.post_state is None:
            # >>
            # To write a block of documentation inside code (called codedoc),
            # start a block of inline comment with ``>> name``::
            #
            #   // >> game/input
            #   // Documentation text goes here.
            #
            # .. codedoc:: docs/codedoc-usage
            if CODEDOC_RE.match(self.buffer[0]):
                match = CODEDOC_RE.match(self.buffer[0])
                file_name = '_codedoc/%s.txt' % match.group(1)
                codedoc = self.last_codedoc = self.root.file(file_name)
                codedoc.add_text(self.buffer[1:])
            # >>
            # The previous codedoc can be added later by starting a block
            # of inline comment with `>>`::
            #
            #   // >> game/input
            #   // Some documentation...
            #
            #   ... /* code */ ...
            #
            #   // >>
            #   // Some more documentation...
            elif self.buffer[0] == '>>':
                self.last_codedoc.add_text(self.buffer[1:])

            # >> docs/moduledoc
            # If a block of inline comment starts directly before an ES6 class,
            # it will be used as the documentation for that class::
            #
            #   // The Progress class holds ...
            #   export class Progress {
            #     constructor() {
            #
            # The line directly after the ``export class`` line should be a
            # ``constructor``, which allows the script to scan the constructor's
            # arguments.
            #
            elif self.match(CLASS_RE):
                module_node = self.module_doc()
                class_node = self.current_class = ClassNode(module_node, self.group(1))
                module_node.add(class_node)
                class_node.add_text(self.buffer)
                self.post_state = 'class'
            # >>
            # If a method definition syntax is found directly after a block of
            # comment, then it will be used for documenting that method::
            # 
            #     // Reports the progress.
            #     report(current, total, extra) {
            elif self.current_class and self.match(METHOD_RE):
                method_node = MethodNode(self.current_class, self.group(1))
                method_node.add_text(self.buffer)
                self.current_class.add(method_node)
            # >>
            # If a getter definition syntax or an assignment to ``this``
            # is found after a comment block, then the comment block documents
            # that attribute::
            # 
            #   constructor() {
            #     // ``true`` if the game is started, ``false`` otherwise.
            #     this.started = false
            #   }
            #
            #   // The song duration in seconds.
            #   get duration() {
            elif self.current_class and (self.match(GETTER_RE) or self.match(ATTRIBUTE_RE)):
                attr_node = AttributeNode(self.current_class, self.group(1))
                attr_node.add_text(self.buffer)
                self.current_class.add(attr_node)
            # >>
            # If ``export let`` is found after a comment block, then the
            # comment block documents that module export::
            # 
            #   // The global SceneManager instance.
            #   export let instance = new SceneManager()
            elif self.match(EXPORT_LET_RE):
                module_node = self.module_doc()
                data_node = DataNode(module_node, self.group(1))
                data_node.add_text(self.buffer)
                module_node.add(data_node)
        elif self.post_state == 'class':
            if self.match(CONSTRUCTOR_RE):
                self.current_class.arguments = self.match(1)

class Node(object):
    def __init__(self, *args):
        self.contents = []
        self.initialize(*args)
    def initialize(self):
        pass
    def add(self, item):
        self.contents.append(item)
    def add_text(self, buf):
        self.contents.append('\n'.join(buf))
    def text_contents(self):
        return '\n\n'.join(map(str, self.contents))
    def __str__(self):
        return self.text_contents()

class RootNode(object):
    def __init__(self):
        self.modules = { }
        self.files = { }
    def file(self, file_name, node_type=Node, *args):
        if file_name in self.files:
            return self.files[file_name]
        else:
            node = self.files[file_name] = node_type(*args)
            return node
    def module(self, module_name):
        if module_name in self.modules:
            return self.modules[module_name]
        else:
            file_name = 'modules/%s.rst' % module_name
            node = self.modules[module_name] = self.file(file_name, ModuleNode, module_name)
            return node

class ModuleNode(Node):
    def initialize(self, name):
        self.name = name
    def __str__(self):
        return (
            self.name + '\n' +
            '=' * len(self.name) + '\n' +
            self.text_contents())

class DomainNode(Node):
    def directive(self):
        pass
    def index(self):
        pass
    def __str__(self):
        return (
            '.. index::\n   single: %s\n\n' % self.index() +
            '.. %s\n   :noindex:\n\n' % self.directive() +
            indent3(self.text_contents()))

class ClassNode(DomainNode):
    def initialize(self, module, name):
        self.name = name
        self.module = module
        self.arguments = ''
    def index(self):
        return '%s; %s' % (self.module.name, self.name)
    def directive(self):
        return 'js:class:: %s(%s)' % (self.name, self.arguments)

class MethodNode(DomainNode):
    def initialize(self, class_node, name):
        self.name = name
        self.class_node = class_node
    def index(self):
        return '%s#%s' % (self.class_node.index(), self.name)
    def directive(self):
        return 'js:function:: %s' % (self.name)

class AttributeNode(DomainNode):
    def initialize(self, class_node, name):
        self.name = name
        self.class_node = class_node
    def index(self):
        return '%s#%s' % (self.class_node.index(), self.name)
    def directive(self):
        return 'js:attribute:: %s' % (self.name)

class DataNode(DomainNode):
    def initialize(self, module, name):
        self.name = name
        self.module = module
    def index(self):
        return '%s; %s' % (self.module.name, self.name)
    def directive(self):
        return 'js:data:: %s' % (self.name)

def main():
    root = RootNode()
    for path in get_source_files():
        processor = FileProcessor(path, root)
        processor.process()
    for filename in root.files:
        mkpath(os.path.dirname(filename))
        print filename
        with open(filename, 'w') as f:
            f.write(str(root.files[filename]))
    with open('modules/index.rst', 'w') as f:
        print >> f, 'Modules Index'
        print >> f, '============='
        print >> f, '.. toctree::'
        print >> f, '   :maxdepth: 2'
        print >> f, ''
        for key in sorted(root.modules):
            print >> f, '   ' + key

if __name__ == '__main__':
    main()