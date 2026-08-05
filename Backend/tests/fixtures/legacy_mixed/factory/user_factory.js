function createUserFromFactory(data) {
  return { id: data.id, name: data.name, createdAt: Date.now() };
}

module.exports = { createUserFromFactory };
