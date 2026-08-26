#!/bin/sh

notion_hook_input=$(cat)
if printf '%s' "$notion_hook_input" | grep -Eiq 'continue|previous|decision|requirement|spec|blocker|roadmap|notion|task|client|counterparty|current status|prior discussion|prior implementation|existing feature|existing task|existing project|alex memory'; then
  printf '%s\n' 'This prompt may need project history. If repository context is insufficient, use notion-context for one targeted search; do not auto-search or load Notion broadly.'
fi
