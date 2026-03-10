/* VEO Pro Max Extension v2.2.2 - Protected */
Object.defineProperty(navigator, 'webdriver', {
get: () => false,
configurable: true,
});
if (window.cdc_adoQpoasnfa76pfcZLmcfl_Array) {
delete window.cdc_adoQpoasnfa76pfcZLmcfl_Array;
}
if (window.cdc_adoQpoasnfa76pfcZLmcfl_Promise) {
delete window.cdc_adoQpoasnfa76pfcZLmcfl_Promise;
}
if (window.cdc_adoQpoasnfa76pfcZLmcfl_Symbol) {
delete window.cdc_adoQpoasnfa76pfcZLmcfl_Symbol;
}
if (navigator.plugins.length === 0) {
Object.defineProperty(navigator, 'plugins', {
get: () => [1, 2, 3, 4, 5],
configurable: true,
});
}
const originalQuery = window.navigator.permissions?.query;
if (originalQuery) {
window.navigator.permissions.query = (parameters) => {
if (parameters.name === 'notifications') {
return Promise.resolve({ state: Notification.permission });
}
return originalQuery.call(window.navigator.permissions, parameters);
};
}