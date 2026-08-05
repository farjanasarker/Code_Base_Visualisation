const { executeCreateUser } = require('../usecases/create_user_usecase');

function adaptCreateUserRequest(httpBody) {
  return executeCreateUser({ id: httpBody.id, name: httpBody.name });
}

module.exports = { adaptCreateUserRequest };
