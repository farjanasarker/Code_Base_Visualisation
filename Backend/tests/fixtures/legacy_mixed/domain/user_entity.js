function createUserEntity(id, name) {
  return { id, name, isValid: () => !!name };
}

module.exports = { createUserEntity };
