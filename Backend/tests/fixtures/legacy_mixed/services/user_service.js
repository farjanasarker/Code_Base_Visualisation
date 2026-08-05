const { findUserById } = require('../repository/user_repository');

function getUserById(id) {
  return findUserById(id);
}

module.exports = { getUserById };
