// The parts of the Firebase web SDK the online editor uses, bundled into public/firebase.js
// (so the page loads nothing from other sites). Rebuild with: node dev/build-sdk.mjs
export { initializeApp } from 'firebase/app';
export { getAuth, GoogleAuthProvider, signInWithPopup, signInWithCredential, signOut, onAuthStateChanged, connectAuthEmulator } from 'firebase/auth';
export {
  initializeFirestore, persistentLocalCache, persistentMultipleTabManager, connectFirestoreEmulator,
  doc, collection, getDoc, getDocs, setDoc, updateDoc, addDoc, deleteDoc, onSnapshot, writeBatch,
  query, where, orderBy, limit, serverTimestamp, deleteField, FieldPath,
} from 'firebase/firestore';
