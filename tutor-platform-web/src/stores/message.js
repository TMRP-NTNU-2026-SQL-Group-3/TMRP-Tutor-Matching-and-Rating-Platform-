import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useMessageStore = defineStore('message', () => {
  const conversations = ref([])

  function setConversations(data) {
    conversations.value = data
  }

  return { conversations, setConversations }
})
