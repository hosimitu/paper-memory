# Summary generation resources

Summary output profiles are defined by paired files:

- `profiles/<id>.json` contains the label, paper kind, automatic-classification guidance and fallback `hints`, profile-specific rules, and section keys/headings/instructions.
- `templates/<id>.md` controls the rendered Markdown layout. Use `{{section:<key>}}` to place a configured section and the shared placeholders `{{title}}`, `{{markdown_link}}`, `{{abstract_original}}`, `{{abstract_translation}}`, `{{author_lines}}`, and `{{tag_lines}}` for shared content.
- `generation_rules.md` holds language, citation, numeric reporting, and shared membrane rules. `dictionary.md` and `convert_units.py` are shared language and unit-conversion resources.

Keep section keys identical between the profile and its Markdown template. The summary generator validates that mapping when it loads profiles. Add a profile by adding both files; Python code should only change when generation or rendering behavior itself changes.

The `research` profile is used for original research papers. Review profiles describe broad overviews, technology comparisons, process/application reviews, material/mechanism reviews, fabrication/evaluation reviews, and modeling/simulation reviews. Automatic selection is the default; a profile can be passed explicitly to override it.
