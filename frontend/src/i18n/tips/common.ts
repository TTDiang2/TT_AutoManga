// Tooltip text shared across the app (page header, sidebar), keyed by control.
// Shown on hover/keyboard focus by components/tooltip/TooltipLayer via a
// data-tip attribute. `zh: typeof en` makes both languages carry every key.
const en = {
  tour: 'Show a quick guided tour of this tab',
};

const zh: typeof en = {
  tour: '快速了解这个页面的导览',
};

export default { en, zh };
