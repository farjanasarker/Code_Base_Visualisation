const { createUserEntity } = require('../domain/user_entity');
const { saveUser } = require('../repository/user_repository');

function executeCreateUser(data) {
  const entity = createUserEntity(data.id, data.name);
  saveUser(entity);
  return entity;
}

module.exports = { executeCreateUser };
