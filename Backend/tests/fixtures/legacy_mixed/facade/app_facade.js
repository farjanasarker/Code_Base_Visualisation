const { getUserById } = require('../services/user_service');
const { executeCreateUser } = require('../usecases/create_user_usecase');
const { createUserFromFactory } = require('../factory/user_factory');
const { getInstance } = require('../singleton/config_singleton');
const { publishEvent } = require('../events/event_bus');

function handleUserWorkflow(data) {
  const config = getInstance();
  const user = createUserFromFactory(data);
  executeCreateUser(user);
  publishEvent({ type: 'user_created', user });
  return getUserById(user.id);
}

module.exports = { handleUserWorkflow };
