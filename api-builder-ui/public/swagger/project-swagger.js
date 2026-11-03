/* Render the selected project's spec with local assets and no external validator. */
const parameters = new URLSearchParams(location.search);
const projectId = parameters.get('project');
const port = parameters.get('port');
const direct = port !== null;
const validPort = port !== null && /^[0-9]+$/.test(port) && Number(port) >= 1 && Number(port) <= 65535;
const localSite = ['localhost', '127.0.0.1', '[::1]'].includes(location.hostname) && ['http:', 'https:'].includes(location.protocol);
if (!projectId || !/^[1-9][0-9]*$/.test(projectId)) {
  document.getElementById('swagger-ui').textContent = 'Choose a project in API Builder first.';
} else if (direct && (!validPort || !localSite)) {
  document.getElementById('swagger-ui').textContent = 'Choose a valid local backend in API Builder Settings first.';
} else {
  const backend = direct ? `${location.protocol}//${location.hostname}:${Number(port)}` : '';
  window.ui = SwaggerUIBundle({
    url: backend + '/api/projects/' + projectId + '/openapi',
    withCredentials: true,
    dom_id: '#swagger-ui',
    deepLinking: true,
    validatorUrl: null,
    supportedSubmitMethods: ['get', 'post', 'patch', 'delete'],
    persistAuthorization: false,
  });
}
