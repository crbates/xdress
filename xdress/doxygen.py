"""Inserts dOxygen documentation into python docstrings. This is done using
the xml export capabilities of dOxygen. The docstrings are inserted into
the desc dictionary for each function/class and will then be merged with
standard auto-docstrings as well as any user input from sidecar files.

This module is available as an xdress plugin by the name
``xdress.doxygen``.

:author: Spencer Lyon <spencerlyon2@gmail.com>

Giving Your Project dOxygen
===========================

This plugin works in two phases:

1. It takes user given doxygen settings (with sane defaults if not
   given) and runs dOxygen on the source project in ``rc.sourcedir``.
2. Alters the description dictionary generated by other xdress
   plugins (mainly ``xdress.autodescribe``) by inserting dOxygen output
   as class, method, and function docstrings in the
   `numpydoc <https://pypi.python.org/pypi/numpydoc>`_ format

Usage
-----

The usage of this plugin is very straightforward and comes in two steps:

1. Add ``xdress.doxygen`` to the list of plugins in your xdressrc.py
2. Define one or both of the (optional) rc variables given below. If
   These are not defined in xdressrc, the plugin will provide some sane
   initial values.

   a. ``doxygen_config``: A python dictionary mapping doxygen keys to
      their desired values. See
      `this <http://www.stack.nl/~dimitri/doxygen/manual/config.html>`_
      page in the dOxygen documentation for more information regarding
      the possible keys.
   b. ``doxyfile_name``: This is the name that should be given to the
      doxygen config file. The file will be written out in the directory
      containing xdressrc.py unless a path is specified for this
      variable. The path is assumed to be relative to the directory
      where ``xdress`` is run. The default value for this variable is
      ``'doxyfile'``.

.. note::

    If you would like to see the default values for ``doxygen_config``,
    try ``from xdress.doxygen import default_doxygen_config``. The
    only changes that need to take place are as follows:
    ``PROJECT_NAME`` is assigned to ``rc.package``,  ``INPUT`` is
    assigned to ``rc.sourcedir`` and ``OUTPUT_DIRECTORY`` is assigned
    to ``rc.builddir``.

The user might accomplish these steps as follows::

   plugins = ('xdress.stlwrap', 'xdress.autoall', 'xdress.autodescribe',
              'xdress.doxygen', 'xdress.cythongen')

   # Set various doxygen configuration keys
   doxygen_config = {'PROJECT_NAME': 'My Awesome Project',
                     'EXTRACT_ALL': False,  # Note usage of python False
                     'GENERATE_DOCBOOK': False,
                     'GENERATE_LATEX': True  # Could be 'YES' or True
                     }

   # Write the config file in the build directory
   doxyfile_name = './build/the_best_doxyfile'

.. warning::

   The most common issue users make with this plugin is including it in
   the plugins list in the wrong order. Because xdress tries to execute
   plugins in the order they are listed in xdressrc, it is important
   that ``xdress.doxygen`` come after ``xdress.autodescribe``, but
   before ``xdress.cythongen``. autodescribe will ensure that the
   description dictionary is in place and ready for dOxygen to alter
   before cythongen has a chance to produce wrapper code.

dOygen API
==========
"""
from __future__ import print_function
import re
import os
import subprocess
from textwrap import TextWrapper
from .plugins import Plugin
from .utils import newoverwrite

# XML conditional imports
try:
    from lxml import etree
except ImportError:
    try:
        # Python 2.5
        import xml.etree.cElementTree as etree
    except ImportError:
        try:
          # Python 2.5
          import xml.etree.ElementTree as etree
        except ImportError:
            try:
                # normal cElementTree install
                import cElementTree as etree
            except ImportError:
                try:
                  # normal ElementTree install
                  import elementtree.ElementTree as etree
                except ImportError:
                    pass
##############################################################################
##
## -- Tools used in parsing
##
##############################################################################
### Set up various TextWrapper instances
# wrap_68 is for the core content of the docstring. It wraps, assuming there
# will be 4 spaces preceding the text. This is suitable for the docstring
# for a class or a function
wrap_68 = TextWrapper(width=68, initial_indent=' ' * 0,
                      subsequent_indent=' ' * 0)

# wrap_64 is for core part of a class method. It wraps, assuming there
# will be 8 spaces preceding the text
wrap_64 = TextWrapper(width=64, initial_indent=' ' * 0,
                      subsequent_indent=' ' * 0)

# attrib_wrap is for listing class attributes/methods
attrib_wrap = TextWrapper(width=64, initial_indent=' ' * 0,
                          subsequent_indent=' ' * 4)

_param_sec = 'Parameters\n----------'
_return_sec = 'Returns\n-------'

# Helpful re to be used when parsing class definitions.
_no_arg_links = re.compile('(<param>\n\s+<type>)<ref.+>(\w+)</ref>(.+</type>)')


##############################################################################
##
## -- Functions to create docstrings
##
##############################################################################
def class_docstr(class_dict, desc_funcs=False):
    """Generate the main docstring for a class given a dictionary of the
    parsed dOxygen xml.

    Parameters
    ----------
    class_dict : dict
        This is a dictionary that should be the return value of the
        function parse_class defined in this module

    desc_funcs : bool, optional(default=False)
        Whether or not to include the brief description of class methods
        in the main list of methods.

    Returns
    -------
    msg : str
        The docstring to be inserted into the desc dictionary for the
        class.

    """
    class_name = class_dict['kls_name'].split('::')[-1]
    cls_msg = class_dict['public-func'][class_name]['detaileddescription']

    msg = wrap_68.fill(cls_msg)

    # Get a list of the methods and variables to list here.
    methods = list(set(class_dict['members']['methods']))
    variables = class_dict['members']['variables']

    ivar_keys = filter(lambda x: 'attrib' in x, class_dict.keys())
    func_grp_keys = filter(lambda x: 'func' in x, class_dict.keys())

    # Flatten instance variables and functions from class dictionary.
    ivar_items = []
    for i in ivar_keys:
        ivar_items += class_dict[i].items()
    ivars = dict(ivar_items)

    func_items = []
    for i in func_grp_keys:
        func_items += class_dict[i].items()
    funcs = dict(func_items)

    # skip a line and begin Attributes section
    msg += '\n\n'
    msg += wrap_68.fill('Attributes')
    msg += '\n'
    msg += wrap_68.fill('----------')
    msg += '\n'

    for i in variables:
        desc = ivars[i]['briefdescription']
        desc += ' ' + ivars[i]['detaileddescription']
        var_msg = '%s (%s) : %s' % (i, ivars[i]['type'], desc.strip())
        msg += attrib_wrap.fill(var_msg)
        msg += '\n'

    # skip a line and begin Methods section
    msg += '\n\n'
    msg += wrap_68.fill('Methods')
    msg += '\n'
    msg += wrap_68.fill('-------')
    msg += '\n'

    # sort them
    methods.sort()

    # Move the destructor from the bottom to be second.
    methods.insert(1, methods.pop())

    for i in methods:
        desc = funcs[i]['briefdescription']
        if len(desc) == 0 or not desc_funcs:
            fun_msg = i
        else:
            fun_msg = '%s : %s' % (i, desc.strip())
        msg += attrib_wrap.fill(fun_msg)
        msg += '\n'

    # skip a line and begin notes section
    msg += '\n'
    msg += wrap_68.fill('Notes')
    msg += '\n'
    msg += wrap_68.fill('-----')
    msg += '\n'

    def_msg = "This class was defined in %s" % (class_dict['file_name'])
    ns_msg = 'The class is found in the "%s" namespace'

    msg += wrap_68.fill(def_msg)
    msg += '\n\n'
    msg += wrap_68.fill(ns_msg % (class_dict['namespace']))

    return msg


def func_docstr(func_dict, is_method=False):
    """Generate the docstring for a function given a dictionary of the
    parsed dOxygen xml.

    Parameters
    ----------
    func_dict : dict
        This is a dictionary that should be the return value of the
        function parse_function defined in this module. If this is a
        class method it can be a sub-dictionary of the return value of
        the parse_class function.

    is_method : bool, optional(default=False)
        Whether or not to the function is a class method. If it is,
        the text will be wrapped 4 spaces earlier to offset additional
        indentation

    Returns
    -------
    msg : str
        The docstring to be inserted into the desc dictionary for the
        function.

    """
    if is_method:
        wrapper = wrap_64
    else:
        wrapper = wrap_68

    detailed_desc = func_dict['detaileddescription']
    brief_desc = func_dict['briefdescription']
    desc = '\n\n'.join([brief_desc, detailed_desc]).strip()

    args = func_dict['args']
    if args is None:
        params = ['None']
    else:
        params = []
        for arg in args:
            arg_str = "%s : %s" % (arg, args[arg]['type'])
            if 'desc' in args[arg]:
                arg_str += '\n%s' % (args[arg]['desc'])
            params.append(arg_str)

    returning = func_dict['ret_type']
    if returning is None:
        rets = ['None']
    else:
        rets = []
        i = 1
        if isinstance(returning, str):
            rets.append('res%i : ' % i + returning)
        else:
            for ret in returning:
                rets.append('res%i : ' % i + ret)
                i += 1

    # put main section in
    msg = wrapper.fill(desc)

    # skip a line and begin parameters section
    msg += '\n\n'
    msg += wrapper.fill('Parameters')
    msg += '\n'
    msg += wrapper.fill('----------')
    msg += '\n'

    # add parameters
    for p in params:
        lines = str.splitlines(p)
        msg += wrapper.fill(lines[0])
        msg += '\n'
        more = False
        for i in range(1, len(lines)):
            more = True
            l = lines[i]
            msg += wrapper.fill(l)

        if more:
            msg += '\n\n'
        else:
            msg += '\n'

    # skip a line and begin returns section
    msg += wrapper.fill('Returns')
    msg += '\n'
    msg += wrapper.fill('-------')
    msg += '\n'

    # add return values
    for r in rets:
        lines = str.splitlines(r)
        msg += wrapper.fill(lines[0])
        msg += '\n'
        for i in range(1, len(lines)):
            l = lines[i]
            msg += wrapper.fill(l)
        msg += '\n'

    # TODO: add notes section like in class function above.
    # # skip a line and begin notes section
    # msg += wrapper.fill('Notes')
    # msg += '\n'
    # msg += wrapper.fill('-----')
    # msg += '\n'

    return msg

##############################################################################
##
## -- dOxygen setup and execution
##
##############################################################################
# this is the meat of the template doxyfile template returned by: doxygen -g
# NOTE: I have changed a few things like no html/latex generation.

# NOTE: Also, there are three placeholders for format: project, output_dir,
#       src_dir
default_doxygen_config = {'DOXYFILE_ENCODING': 'UTF-8',
                          'PROJECT_NAME': 'project',
                          'PROJECT_NUMBER': '"0.1"',
                          'OUTPUT_DIRECTORY': 'output_dir',
                          'CREATE_SUBDIRS': 'NO',
                          'OUTPUT_LANGUAGE': 'English',
                          'BRIEF_MEMBER_DESC': 'YES',
                          'REPEAT_BRIEF': 'YES',
                          'ALWAYS_DETAILED_SEC': 'NO',
                          'INLINE_INHERITED_MEMB': 'NO',
                          'FULL_PATH_NAMES': 'YES',
                          'SHORT_NAMES': 'NO',
                          'JAVADOC_AUTOBRIEF': 'NO',
                          'QT_AUTOBRIEF': 'NO',
                          'MULTILINE_CPP_IS_BRIEF': 'NO',
                          'INHERIT_DOCS': 'YES',
                          'SEPARATE_MEMBER_PAGES': 'NO',
                          'TAB_SIZE': '4',
                          'OPTIMIZE_OUTPUT_FOR_C': 'NO',
                          'OPTIMIZE_OUTPUT_JAVA': 'NO',
                          'OPTIMIZE_FOR_FORTRAN': 'NO',
                          'OPTIMIZE_OUTPUT_VHDL': 'NO',
                          'MARKDOWN_SUPPORT': 'YES',
                          'AUTOLINK_SUPPORT': 'YES',
                          'BUILTIN_STL_SUPPORT': 'NO',
                          'CPP_CLI_SUPPORT': 'NO',
                          'SIP_SUPPORT': 'NO',
                          'IDL_PROPERTY_SUPPORT': 'YES',
                          'DISTRIBUTE_GROUP_DOC': 'NO',
                          'SUBGROUPING': 'YES',
                          'INLINE_GROUPED_CLASSES': 'NO',
                          'INLINE_SIMPLE_STRUCTS': 'NO',
                          'TYPEDEF_HIDES_STRUCT': 'NO',
                          'LOOKUP_CACHE_SIZE': '0',
                          'EXTRACT_ALL': 'NO',
                          'EXTRACT_PRIVATE': 'NO',
                          'EXTRACT_PACKAGE': 'NO',
                          'EXTRACT_STATIC': 'NO',
                          'EXTRACT_LOCAL_CLASSES': 'YES',
                          'EXTRACT_LOCAL_METHODS': 'NO',
                          'EXTRACT_ANON_NSPACES': 'NO',
                          'HIDE_UNDOC_MEMBERS': 'NO',
                          'HIDE_UNDOC_CLASSES': 'NO',
                          'HIDE_FRIEND_COMPOUNDS': 'NO',
                          'HIDE_IN_BODY_DOCS': 'NO',
                          'INTERNAL_DOCS': 'NO',
                          'CASE_SENSE_NAMES': 'NO',
                          'HIDE_SCOPE_NAMES': 'NO',
                          'SHOW_INCLUDE_FILES': 'YES',
                          'FORCE_LOCAL_INCLUDES': 'NO',
                          'INLINE_INFO': 'YES',
                          'SORT_MEMBER_DOCS': 'YES',
                          'SORT_BRIEF_DOCS': 'NO',
                          'SORT_MEMBERS_CTORS_1ST': 'NO',
                          'SORT_GROUP_NAMES': 'NO',
                          'SORT_BY_SCOPE_NAME': 'NO',
                          'STRICT_PROTO_MATCHING': 'NO',
                          'GENERATE_TODOLIST': 'YES',
                          'GENERATE_TESTLIST': 'YES',
                          'GENERATE_BUGLIST': 'YES',
                          'GENERATE_DEPRECATEDLIST': 'YES',
                          'MAX_INITIALIZER_LINES': '30',
                          'SHOW_USED_FILES': 'YES',
                          'SHOW_FILES': 'YES',
                          'SHOW_NAMESPACES': 'YES',
                          'QUIET': 'YES',
                          'WARNINGS': 'YES',
                          'WARN_IF_UNDOCUMENTED': 'NO',
                          'WARN_IF_DOC_ERROR': 'YES',
                          'WARN_NO_PARAMDOC': 'NO',
                          'WARN_FORMAT': '"$file:$line: $text"',
                          'INPUT': '{src_dir}',
                          'INPUT_ENCODING': 'UTF-8',
                          'RECURSIVE': 'NO',
                          'EXCLUDE_SYMLINKS': 'NO',
                          'EXAMPLE_RECURSIVE': 'NO',
                          'FILTER_SOURCE_FILES': 'NO',
                          'SOURCE_BROWSER': 'NO',
                          'INLINE_SOURCES': 'NO',
                          'STRIP_CODE_COMMENTS': 'YES',
                          'REFERENCED_BY_RELATION': 'NO',
                          'REFERENCES_RELATION': 'NO',
                          'REFERENCES_LINK_SOURCE': 'YES',
                          'USE_HTAGS': 'NO',
                          'VERBATIM_HEADERS': 'YES',
                          'ALPHABETICAL_INDEX': 'YES',
                          'COLS_IN_ALPHA_INDEX': '5',
                          'GENERATE_HTML': 'NO',
                          'HTML_OUTPUT': 'html',
                          'HTML_FILE_EXTENSION': '.html',
                          'HTML_COLORSTYLE_HUE': '220',
                          'HTML_COLORSTYLE_SAT': '100',
                          'HTML_COLORSTYLE_GAMMA': '80',
                          'HTML_TIMESTAMP': 'YES',
                          'HTML_DYNAMIC_SECTIONS': 'NO',
                          'HTML_INDEX_NUM_ENTRIES': '100',
                          'GENERATE_DOCSET': 'NO',
                          'DOCSET_FEEDNAME': '"Doxygen generated docs"',
                          'DOCSET_BUNDLE_ID': 'org.doxygen.Project',
                          'DOCSET_PUBLISHER_ID': 'org.doxygen.Publisher',
                          'DOCSET_PUBLISHER_NAME': 'Publisher',
                          'GENERATE_HTMLHELP': 'NO',
                          'GENERATE_CHI': 'NO',
                          'BINARY_TOC': 'NO',
                          'TOC_EXPAND': 'NO',
                          'GENERATE_QHP': 'NO',
                          'QHP_NAMESPACE': 'org.doxygen.Project',
                          'QHP_VIRTUAL_FOLDER': 'doc',
                          'GENERATE_ECLIPSEHELP': 'NO',
                          'ECLIPSE_DOC_ID': 'org.doxygen.Project',
                          'DISABLE_INDEX': 'NO',
                          'GENERATE_TREEVIEW': 'NO',
                          'ENUM_VALUES_PER_LINE': '4',
                          'TREEVIEW_WIDTH': '250',
                          'EXT_LINKS_IN_WINDOW': 'NO',
                          'FORMULA_FONTSIZE': '10',
                          'FORMULA_TRANSPARENT': 'YES',
                          'USE_MATHJAX': 'NO',
                          'MATHJAX_FORMAT': 'HTML-CSS',
                          'MATHJAX_RELPATH': 'http://cdn.mathjax.org/mathjax/latest',
                          'SEARCHENGINE': 'YES',
                          'SERVER_BASED_SEARCH': 'NO',
                          'EXTERNAL_SEARCH': 'NO',
                          'SEARCHDATA_FILE': 'searchdata.xml',
                          'GENERATE_LATEX': 'NO',
                          'LATEX_OUTPUT': 'latex',
                          'LATEX_CMD_NAME': 'latex',
                          'MAKEINDEX_CMD_NAME': 'makeindex',
                          'COMPACT_LATEX': 'NO',
                          'PAPER_TYPE': 'a4',
                          'PDF_HYPERLINKS': 'YES',
                          'USE_PDFLATEX': 'YES',
                          'LATEX_BATCHMODE': 'NO',
                          'LATEX_HIDE_INDICES': 'NO',
                          'LATEX_SOURCE_CODE': 'NO',
                          'LATEX_BIB_STYLE': 'plain',
                          'GENERATE_RTF': 'NO',
                          'RTF_OUTPUT': 'rtf',
                          'COMPACT_RTF': 'NO',
                          'RTF_HYPERLINKS': 'NO',
                          'GENERATE_MAN': 'NO',
                          'MAN_OUTPUT': 'man',
                          'MAN_EXTENSION': '.3',
                          'MAN_LINKS': 'NO',
                          'GENERATE_XML': 'YES',
                          'XML_OUTPUT': 'xml',
                          'XML_PROGRAMLISTING': 'YES',
                          'GENERATE_DOCBOOK': 'NO',
                          'DOCBOOK_OUTPUT': 'docbook',
                          'GENERATE_AUTOGEN_DEF': 'NO',
                          'GENERATE_PERLMOD': 'NO',
                          'PERLMOD_LATEX': 'NO',
                          'PERLMOD_PRETTY': 'YES',
                          'ENABLE_PREPROCESSING': 'YES',
                          'MACRO_EXPANSION': 'NO',
                          'EXPAND_ONLY_PREDEF': 'NO',
                          'SEARCH_INCLUDES': 'YES',
                          'SKIP_FUNCTION_MACROS': 'YES',
                          'ALLEXTERNALS': 'NO',
                          'EXTERNAL_GROUPS': 'YES',
                          'EXTERNAL_PAGES': 'YES',
                          'PERL_PATH': '/usr/bin/perl',
                          'CLASS_DIAGRAMS': 'YES',
                          'HIDE_UNDOC_RELATIONS': 'YES',
                          'HAVE_DOT': 'NO',
                          'DOT_NUM_THREADS': '0',
                          'DOT_FONTNAME': 'Helvetica',
                          'DOT_FONTSIZE': '10',
                          'CLASS_GRAPH': 'YES',
                          'COLLABORATION_GRAPH': 'YES',
                          'GROUP_GRAPHS': 'YES',
                          'UML_LOOK': 'NO',
                          'UML_LIMIT_NUM_FIELDS': '10',
                          'TEMPLATE_RELATIONS': 'NO',
                          'INCLUDE_GRAPH': 'YES',
                          'INCLUDED_BY_GRAPH': 'YES',
                          'CALL_GRAPH': 'NO',
                          'CALLER_GRAPH': 'NO',
                          'GRAPHICAL_HIERARCHY': 'YES',
                          'DIRECTORY_GRAPH': 'YES',
                          'DOT_IMAGE_FORMAT': 'png',
                          'INTERACTIVE_SVG': 'NO',
                          'DOT_GRAPH_MAX_NODES': '50',
                          'MAX_DOT_GRAPH_DEPTH': '0',
                          'DOT_TRANSPARENT': 'NO',
                          'DOT_MULTI_TARGETS': 'NO',
                          'GENERATE_LEGEND': 'NO',
                          'DOT_CLEANUP': 'YES'}
##############################################################################
##
## -- Functions to parse the xml
##
##############################################################################


def parse_index_xml(index_path):
    """Parses index.xml to get list of dictionaries for class and function
    names. Each dictionary will have as keys the object (function
    or class) names and the values will be dictionaries with (at least)
    key-value pairs representing the .xml file name where the
    information for that object can be found.

    Parameters
    ----------
    index_path : str
        The path to index.xml. This is most likely to be provided by the
        run control instance.

    Returns
    classes : dict
        A dictionary of dictionaries, one for each class.

    funcs : dict
        A dictionary of dictionaries, one for each function.
    """
    if not index_path.endswith('index.xml'):
        if index_path[-1] != os.path.sep:
            index_path += os.path.sep + 'index.xml'
        else:
            index_path += 'index.xml'
    root = etree.parse(index_path)

    funcs = {}
    classes = {}

    class_list = filter(lambda i: i.attrib['kind'] == 'class',
                        root.iter('compound'))

    namespaces = filter(lambda i: i.attrib['kind'] == 'namespace',
                        root.iter('compound'))

    for i in namespaces:
        ns_name = i.find('name').text
        ns_file_name = 'namespace%s.xml' % (ns_name)
        ns_funcs = filter(lambda x: x.attrib['kind'] == 'function',
                          i.iter('member'))

        # Create counter dict to keep track of duplicate names
        f_name_cnts = {}
        for k in ns_funcs:
            f_name = k.find('name').text
            refid = k.attrib['refid']

            # Change the name if necessary
            if f_name in f_name_cnts.keys():
                orig = str(f_name)
                f_name += str(f_name_cnts[f_name])
                f_name_cnts[orig] += 1
            else:
                f_name_cnts[f_name] = 1

            funcs[f_name] = {'file_name': ns_file_name, 'refid': refid,
                             'namespace': ns_name}

    for kls in class_list:
        kls_defn = kls.find('name').text.split('::')
        kls_ns = '::'.join(kls_defn[:-1])
        kls_name = kls_defn[-1]
        file_name = kls.attrib['refid']
        kls_dict = {'file_name': file_name, 'namespace': kls_ns, 'vars': [],
                    'methods': []}

        for mem in kls.iter('member'):
            mem_name = mem.find('name').text
            if mem.attrib['kind'] == 'variable':
                kls_dict['vars'].append(mem_name)
            elif mem.attrib['kind'] == 'function':
                kls_dict['methods'].append(mem_name)

        classes[kls_name] = kls_dict

    return classes, funcs


def fix_xml_links(file_name):
    """For some reason I can't get doxygen to remove hyperlinks to members
    defined in the same file. This messes up the parsing. To overcome this
    I will just use a little regex magic to do it myself.
    """
    # Get exiting file and read it in
    ff = open(file_name, 'r')
    text = ff.read()
    ff.close()

    # make the substitutions, re-write the file, and close
    new_text = _no_arg_links.sub('\g<1>\g<2>\g<3>', text)
    ff = open(file_name, 'w')
    ff.write(new_text)
    ff.close()


def _parse_func(f_xml):
    """Parse a function given the xml representation of it.
    """
    mem_dict = {}

    # Find detailed description
    mem_dd = f_xml.find('detaileddescription')
    dd_paras = mem_dd.findall('para')
    num_dd_paras = len(dd_paras)
    if num_dd_paras == 1:
        mem_ddstr = dd_paras[0].text

        # We need arg_dict around to check for later
        arg_dict = None
    elif num_dd_paras == 2:
        # first one will have normal text
        mem_ddstr = dd_paras[0].text

        # Second one will have details regarding function args
        arg_para = dd_paras[1]
        arg_dict = {}
        for i in arg_para.find('parameterlist').findall('parameteritem'):
            a_name = i.find('parameternamelist').find('parametername').text
            a_desc = i.find('parameterdescription').find('para').text
            arg_dict[a_name] = a_desc
    else:
        # Didn't find anything, so just make an empty string
        mem_ddstr = ''

        # We need arg_dict around to check for later
        arg_dict = None

    mem_dict['detaileddescription'] = mem_ddstr

    # Get return type
    mem_dict['ret_type'] = f_xml.find('type').text

    # Get argument types and names
    args = {}
    for param in f_xml.findall('param'):
        # add tuple of  arg type, arg name to arg_types list
        arg_name = param.find('declname').text
        arg_type = param.find('type').text
        args[arg_name] = {'type': arg_type}
        if arg_dict is not None:
            # Add argument descriptions we just pulled out
            args[arg_name]['desc'] = arg_dict[arg_name]

    args = None if len(args) == 0 else args
    mem_dict['args'] = args

    # Get function signature
    mem_argstr = f_xml.find('argsstring').text
    mem_dict['arg_string'] = mem_argstr

    return mem_dict


def _parse_variable(v_xml):
    """Parse a variable given the xml representation of it.
    """
    mem_dict = {}

    # Find detailed description
    mem_dd = v_xml.find('detaileddescription')
    try:
        mem_ddstr = mem_dd.find('para').text
    except AttributeError:
        mem_ddstr = ''

    mem_dict['detaileddescription'] = mem_ddstr

    mem_dict['type'] = v_xml.find('type').text

    return mem_dict


def _parse_common(xml, the_dict):
    """
    Parse things in common for both variables and functions. This should
    be run after a more specific function like _parse_func or
    _parse_variable because it needs a member dictionary as an input.

    Parameters
    ----------
    xml : etree.Element
        The xml representation for the member you would like to parse

    the_dict : dict
        The dictionary that has already been filled with more specific
        data. This dictionary is modified in-place and an updated
        version is returned.

    Returns
    -------
    the_dict : dict
        The member dictionary that has been updated with the
        briefdescription and definition keys.
    """
    # Find brief description
    mem_bd = xml.find('briefdescription')
    try:
        mem_bdstr = mem_bd.find('para').text
        mem_bdstr = mem_bdstr if mem_bdstr is not None else ''
    except AttributeError:
        mem_bdstr = ''
    the_dict['briefdescription'] = mem_bdstr

    # add member definition
    the_dict['definition'] = xml.find('definition').text

    return the_dict


def parse_function(func_dict):
    """Takes a dictionary defining where the xml for the function is, does
    some function specific parsing and returns a new dictionary with
    the parsed xml.
    """
    root = etree.parse(func_dict['file_name'])
    f_id = func_dict['refid']
    compd_def = root.find('compounddef')
    func_sec = filter(lambda x: x.attrib['kind'] == 'func',
                      compd_def.iter('sectiondef'))[0]

    this_func = filter(lambda x: x.attrib['id'] == f_id,
                       func_sec.iter('memberdef'))[0]

    ret_dict = _parse_func(this_func)

    return _parse_common(this_func, ret_dict)


def parse_class(class_dict):
    """Parses a single class and returns a dictionary of dictionaries
    containing all the data for that class.

    Parameters
    ----------
    class_dict : dict
        A dictionary containing the following keys:
        ['file_name', 'methods', 'vars']

    Returns
    -------
    data : dict
        A dictionary with all docstrings for instance variables and
        class methods. This object is structured as follows::

            data
                'protected-func'
                    'prot_func1'
                        arg_string
                        args
                        briefdescription
                        detaileddescription
                        ret_type
                        definition

                'public-func'
                    'pub_func_1'
                        arg_string
                        args
                        briefdescription
                        detaileddescription
                        ret_type
                        definition

                'protected-attrib'
                    'prot-attrib1'
                        briefdescription
                        detaileddescription
                        type
                        definition

        This means that data is a 3-level dictionary. The levels go as
        follows:

        1. data

            - keys: Some of the following (more?): 'protected-func',
              'protected-attrib', 'public-func',  'public-static-attrib',
              'publib-static-func', 'public-type'
            - values: dictionaries of attribute types

        2. dictionaries of attribute types

            - keys: attribute names
            - values: attribute dictionaries

        3. attribute dictionaries

            - keys: arg_string, args, briefdescription, type, definition
              detaileddescription,
            - values: objects containing the actual data we care about

    Notes
    -----
    The inner 'arg_string' key is only applicable to methods as it
    contains the function signature for the arguments.

    """
    c1 = class_dict
    fn = c1['file_name'] + '.xml'

    fix_xml_links(fn)

    croot = etree.parse(fn)
    compd_def = croot.find('compounddef')
    data = {}
    for sec in compd_def.iter('sectiondef'):
        # Iterate over all sections in the compound
        sec_name = sec.attrib['kind']
        sec_dict = {}

        for mem in sec.iter('memberdef'):
            # Iterate over each member in the section
            # get the kind. Will usually be variable or function.
            m_kind = mem.attrib['kind']

            if m_kind == 'function':
                # do special stuff for functions
                mem_dict = _parse_func(mem)

            elif m_kind == 'variable':
                mem_dict = _parse_variable(mem)

            mem_dict = _parse_common(mem, mem_dict)

            mem_name = mem.find('name').text

            # Avoid overwriting methods with multiple implementations
            # (especially constructors)
            i = 1
            while mem_name in sec_dict.keys():
                if i > 1:
                    mem_name = mem_name[:-1]
                mem_name += str(i)
                i += 1

            sec_dict[mem_name] = mem_dict

        data[sec_name] = sec_dict

    data['kls_name'] = compd_def.find('compoundname').text

    data['members'] = {}
    data['members']['methods'] = class_dict['methods']
    data['members']['variables'] = class_dict['vars']

    c_fn = compd_def.find('location').attrib['file'].split(os.path.sep)[-1]
    data['file_name'] = c_fn

    ns = '::'.join(compd_def.find('compoundname').text.split('::')[:-1])
    data['namespace'] = ns

    return data

##############################################################################
##
## -- Put it all together in a plugin! :)
##
##############################################################################

_overload_msg = \
"""
This {f_type} was overloaded in the C-based source. To overcome this we
ill put the relevant docstring for each version below. Each version will begin
with a line of # characters.
"""


def merge_configs(old, new):
    d = dict(old)
    d.update(new)
    return d


def dox_dict2str(dox_dict):
    s = ""
    new_line = '{option} = {value}\n'
    for key, value in dox_dict.items():

        if value is True:
            _value = 'YES'
        elif value is False:
            _value = 'NO'
        else:
            _value = value

        s += new_line.format(option=key.upper(), value=_value)

    # Don't need an empty line at the end
    return s.strip()


class XDressPlugin(Plugin):
    """
    Add python docstrings (in numpydoc format) from dOxygen markup in
    the source to the generated cython wrapper.
    """

    # needs autodescribe to populate rc.classes, rc.functions, ect.
    requires = ('xdress.base', 'xdress.autodescribe')

    defaultrc = {"doxygen_config": default_doxygen_config,
                 "doxyfile_name": 'doxyfile'}

    rcupdaters = {'doxygen_config': merge_configs}

    def setup(self, rc):
        """Need setup method to get project, output_dir, and src_dir from
        rc and put them in the default_doxygen_config before running
        doxygen
        """
        rc_params = {'PROJECT_NAME': rc.package,
                     'OUTPUT_DIRECTORY': rc.builddir,
                     'INPUT': rc.sourcedir}
        rc.doxygen_config.update(rc_params)

    def execute(self, rc):
        """Runs doxygen to produce the xml, then parses it and adds
        docstrings to the desc dictionary.
        """
        print("doxygen: Running dOxygen")

        build_dir = rc.builddir

        # Create the doxyfile
        doxyfile = dox_dict2str(rc.doxygen_config)
        newoverwrite(doxyfile, rc.doxyfile_name)

        # Run doxygen
        subprocess.call(['doxygen', rc.doxyfile_name])

        xml_dir = build_dir + os.path.sep + 'xml'
        # Parse index.xml and obtain list of classes and functions
        print("doxygen: Adding dOxygen to docstrings")
        classes, funcs = parse_index_xml(xml_dir + os.path.sep + 'index.xml')

        # Go for the classes!
        for c in rc.classes:
            kls = c[0]
            kls_mod = c[2]

            # Parse the class
            try:
                this_kls = classes[kls]
            except KeyError:
                print("Couldn't find class %s in xml. Skipping it - " % (str(kls))
                      + "it will not appear in wrapper docstrings.")
                continue

            prepend_fn = build_dir + os.path.sep + 'xml' + os.path.sep
            this_kls['file_name'] = prepend_fn + this_kls['file_name']
            parsed = parse_class(this_kls)

            # Make docstrings dictionary if needed
            if 'docstrings' not in rc.env[kls_mod][kls].keys():
                rc.env[kls_mod][kls]['docstrings'] = {}
                rc.env[kls_mod][kls]['docstrings']['methods'] = {}

            # Add class docstring
            rc.env[kls_mod][kls]['docstrings']['class'] = class_docstr(parsed)

            # Grab list of methods in rc.env
            rc_methods = [i[0] for i in rc.env[kls_mod][kls]['methods'].keys()]

            # Grab function group keys from parsed dOxygen
            func_grp_keys = filter(lambda x: 'func' in x, parsed.keys())

            # Loop over rc.env methods and try to match them with dOxygen
            for m in rc_methods:
                matches = []
                for key in func_grp_keys:
                    try:
                        # Grab the method dictionary and extend matches list
                        m_names = filter(lambda x: x.startswith(m), parsed[key].keys())
                        matches.extend(parsed[key][i] for i in m_names)
                    except KeyError:
                        # Just try a different key and move on
                        continue

                if len(matches) == 1:
                    m_ds = func_docstr(matches[0], is_method=True)
                    # m_ds = '\n\n' + m_ds
                    rc.env[kls_mod][kls]['docstrings']['methods'][m] = m_ds
                elif len(matches) > 1:
                    ds_list = [func_docstr(i, is_method=True) for i in matches]
                    m_ds = _overload_msg.format(f_type='method')
                    m_ds = wrap_64.fill(m_ds)
                    m_ds += '\n\n'

                    ds = str('#' * 64 + '\n\n').join(ds_list)
                    m_ds += ds

                    rc.env[kls_mod][kls]['docstrings']['methods'][m] = m_ds
                else:
                    print("Couldn't find method %s in xml. Skipping it" % (m)
                          + " - it will not appear in wrapper docstrings.")
                    continue

        # And on to the functions.
        for f in rc.functions:
            func = f[0]
            func_mod = f[2]

            # Pull out all parsed names that match the function name
            # This is necessary because overloaded funcs will have
            # multiple entries
            matches = filter(lambda x: f in x, funcs.keys())

            if matches is not None:
                if len(matches) == 1:
                    f_ds = func_docstr(parse_function(funcs[f]))
                else:
                    # Overloaded function
                    print('HERE OVERLOADING!')
                    ds_list = [func_docstr(parse_function(funcs[i]))
                               for i in matches]
                    f_ds = _overload_msg.format(f_type='function')
                    f_ds = wrap_68.fill(f_ds)
                    f_ds += '\n\n'
                    ds = str('\n\n' + '#' * 72 + '\n\n').join(ds_list)
                    f_ds += ds

                rc.env[func_mod][func]['docstring'] = f_ds

            else:
                print("Couldn't find function %s in xml. Skipping it" % (func)
                      + " - it will not appear in wrapper docstrings.")
                continue


        # TODO: Add the docstrings we found to the descriptions cache.
        #       This is probably easier to do as I am putting them in the
        #       rc.env places
