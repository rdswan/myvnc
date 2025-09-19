# This file must be used with "source bin/activate.csh" *from csh*.
# You cannot run it directly.
# Created by Davide Di Blasi <davidedb@gmail.com>.
# Ported to Python 3.3 venv by Andrew Svetlov <andrew.svetlov@gmail.com>

alias deactivate 'test $?_OLD_VIRTUAL_PATH != 0 && setenv PATH "$_OLD_VIRTUAL_PATH" && unset _OLD_VIRTUAL_PATH; rehash; test $?_OLD_VIRTUAL_PROMPT != 0 && set prompt="$_OLD_VIRTUAL_PROMPT" && unset _OLD_VIRTUAL_PROMPT; unsetenv VIRTUAL_ENV; test "\!:*" != "nondestructive" && unalias deactivate'

# Unset irrelevant variables.
deactivate nondestructive

# Determine VIRTUAL_ENV dynamically
# This script is located at <project>/.venv_py3/bin/activate.csh
# We need to find the .venv_py3 directory that contains this script

# Strategy: Look for the .venv_py3 directory that contains a bin/activate.csh file (this script)
set _venv_found = ""

# Check current directory and parent directories for .venv_py3/bin/activate.csh
if ( -f ".venv_py3/bin/activate.csh" ) then
    set _venv_found = "`pwd`/.venv_py3"
else if ( -f "tools_src/myvnc/.venv_py3/bin/activate.csh" ) then
    set _venv_found = "`pwd`/tools_src/myvnc/.venv_py3"
else if ( -f "../.venv_py3/bin/activate.csh" ) then
    set _venv_found = "`cd .. && pwd`/.venv_py3"
else if ( -f "../../.venv_py3/bin/activate.csh" ) then
    set _venv_found = "`cd ../.. && pwd`/.venv_py3"
else
    # Search up the directory tree for .venv_py3/bin/activate.csh
    set _current = "`pwd`"
    while ( "$_current" != "/" && "$_venv_found" == "" )
        if ( -f "$_current/.venv_py3/bin/activate.csh" ) then
            set _venv_found = "$_current/.venv_py3"
        else
            set _current = "`dirname $_current`"
        endif
    end
    unset _current
endif

if ( "$_venv_found" != "" ) then
    setenv VIRTUAL_ENV "$_venv_found"
else
    # Fallback: assume .venv_py3 in current directory
    setenv VIRTUAL_ENV "`pwd`/.venv_py3"
endif

unset _venv_found

set _OLD_VIRTUAL_PATH="$PATH"
setenv PATH "$VIRTUAL_ENV/bin:$PATH"


set _OLD_VIRTUAL_PROMPT="$prompt"

if (! "$?VIRTUAL_ENV_DISABLE_PROMPT") then
    if (".venv_py3" != "") then
        set env_name = ".venv_py3"
    else
        if (`basename "VIRTUAL_ENV"` == "__") then
            # special case for Aspen magic directories
            # see http://www.zetadev.com/software/aspen/
            set env_name = `basename \`dirname "$VIRTUAL_ENV"\``
        else
            set env_name = `basename "$VIRTUAL_ENV"`
        endif
    endif
    set prompt = "[$env_name] $prompt"
    unset env_name
endif

alias pydoc python -m pydoc

rehash
