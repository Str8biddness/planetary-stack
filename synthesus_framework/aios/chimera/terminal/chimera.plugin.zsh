#!/usr/bin/env zsh
# Chimera Terminal AI Integration

chimera_ai_precmd() {
    local exit_code=$?
    if [ ! -z "$chimera_ai_enabled" ]; then
        local current_command=$(fc -ln -1)
        local ai_response=$(python3 /opt/chimera/terminal/ai_helper.py "$current_command" $exit_code)
        echo "[Chimera AI]: $ai_response"
    fi
}

autoload -Uz add-zsh-hook
add-zsh-hook precmd chimera_ai_precmd

# Toggle AI with Ctrl+X
zle -N toggle_chimera_ai
toggle_chimera_ai() {
    if [ -z "$chimera_ai_enabled" ]; then
        export chimera_ai_enabled=1
        echo "Chimera AI enabled"
    else
        unset chimera_ai_enabled
        echo "Chimera AI disabled"
    fi
}
bindkey '^X' toggle_chimera_ai
