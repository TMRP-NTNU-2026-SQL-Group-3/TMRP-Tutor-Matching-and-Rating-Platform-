import api from './index'

export const messagesApi = {
  createConversation(targetUserId) {
    return api.post('/api/messages/conversations', { target_user_id: targetUserId })
  },
  listConversations() {
    return api.get('/api/messages/conversations')
  },
  getMessages(conversationId) {
    return api.get(`/api/messages/conversations/${conversationId}`)
  },
  sendMessage(conversationId, content) {
    return api.post(`/api/messages/conversations/${conversationId}`, { content })
  },
  search(query) {
    return api.get('/api/messages/search', { params: { q: query } })
  }
}
