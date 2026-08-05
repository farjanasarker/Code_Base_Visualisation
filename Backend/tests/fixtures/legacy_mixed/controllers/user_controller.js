const { getUserById } = require('../services/user_service');

function handleGetUser(req, res) {
  const user = getUserById(req.params.id);
  res.json(user);
}

module.exports = { handleGetUser };
