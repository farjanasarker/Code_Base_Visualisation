let instance = null;

function getInstance() {
  if (!instance) {
    instance = { loaded: true };
  }
  return instance;
}

module.exports = { getInstance };
