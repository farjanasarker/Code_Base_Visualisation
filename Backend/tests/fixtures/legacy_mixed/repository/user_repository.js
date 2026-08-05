const { queryDatabase } = require('../infra/db_client');

function findUserById(id) {
  return queryDatabase('users', id);
}

function saveUser(user) {
  return queryDatabase('users', user, 'insert');
}

module.exports = { findUserById, saveUser };
